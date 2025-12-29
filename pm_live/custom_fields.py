"""Custom field definitions and utilities for project fields."""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


# Field type constants
FIELD_TYPE_TEXT = "text"
FIELD_TYPE_NUMBER = "number"
FIELD_TYPE_DATE = "date"
FIELD_TYPE_SINGLE_SELECT = "single_select"

FIELD_TYPES = [FIELD_TYPE_TEXT, FIELD_TYPE_NUMBER, FIELD_TYPE_DATE, FIELD_TYPE_SINGLE_SELECT]

# Field type display names
FIELD_TYPE_DISPLAY = {
    FIELD_TYPE_TEXT: "text",
    FIELD_TYPE_NUMBER: "number",
    FIELD_TYPE_DATE: "date",
    FIELD_TYPE_SINGLE_SELECT: "single select",
}

# Number format constants
NUMBER_FORMAT_PLAIN = "number"
NUMBER_FORMAT_CURRENCY = "currency"
NUMBER_FORMAT_PERCENTAGE = "percentage"

NUMBER_FORMATS = [NUMBER_FORMAT_PLAIN, NUMBER_FORMAT_CURRENCY, NUMBER_FORMAT_PERCENTAGE]


@dataclass
class SelectOption:
    """Option for single select field type."""
    value: str
    color: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        result = {"value": self.value}
        if self.color:
            result["color"] = self.color
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "SelectOption":
        """Create from dictionary."""
        return cls(
            value=data.get("value", ""),
            color=data.get("color")
        )


@dataclass
class CustomField:
    """Definition of a custom project field."""
    key: str  # Internal identifier (e.g., "timeframe", "budget")
    label: str  # Display name (e.g., "Timeframe", "Budget")
    field_type: str  # One of FIELD_TYPES
    visible: bool = True
    required: bool = False
    order: int = 0

    # Number field specific
    number_format: str = NUMBER_FORMAT_PLAIN
    currency_symbol: str = "$"

    # Single select field specific
    select_options: List[SelectOption] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        result = {
            "key": self.key,
            "label": self.label,
            "field_type": self.field_type,
            "visible": self.visible,
            "required": self.required,
            "order": self.order,
            "number_format": self.number_format,
            "currency_symbol": self.currency_symbol,
        }

        if self.field_type == FIELD_TYPE_SINGLE_SELECT:
            result["select_options"] = [opt.to_dict() for opt in self.select_options]

        return result

    @classmethod
    def from_dict(cls, data: dict) -> "CustomField":
        """Create from dictionary."""
        select_options = []
        if data.get("field_type") == FIELD_TYPE_SINGLE_SELECT:
            select_options = [
                SelectOption.from_dict(opt)
                for opt in data.get("select_options", [])
            ]

        return cls(
            key=data.get("key", ""),
            label=data.get("label", ""),
            field_type=data.get("field_type", FIELD_TYPE_TEXT),
            visible=data.get("visible", True),
            required=data.get("required", False),
            order=data.get("order", 0),
            number_format=data.get("number_format", NUMBER_FORMAT_PLAIN),
            currency_symbol=data.get("currency_symbol", "$"),
            select_options=select_options,
        )


def create_default_timeframe_field() -> CustomField:
    """Create the default timeframe custom field."""
    return CustomField(
        key="timeframe",
        label="Timeframe",
        field_type=FIELD_TYPE_SINGLE_SELECT,
        visible=True,
        required=False,
        order=0,
        select_options=[
            SelectOption(value="None"),
            SelectOption(value="▬", color="cyan"),
            SelectOption(value="▬ ▬", color="cyan"),
            SelectOption(value="▬ ▬ ▬", color="cyan"),
        ]
    )


def create_default_priority_field() -> CustomField:
    """Create the default priority custom field."""
    return CustomField(
        key="priority",
        label="Priority",
        field_type=FIELD_TYPE_SINGLE_SELECT,
        visible=True,
        required=False,
        order=1,
        select_options=[
            SelectOption(value="!!!", color="red"),
            SelectOption(value="!!", color="yellow"),
            SelectOption(value="!", color="green"),
        ],
    )


def create_default_area_field() -> CustomField:
    """Create the default area custom field."""
    return CustomField(
        key="area",
        label="Area",
        field_type=FIELD_TYPE_SINGLE_SELECT,
        visible=True,
        required=False,
        order=2,
        select_options=[
            SelectOption(value="Work", color="cyan"),
            SelectOption(value="Personal", color="magenta"),
        ],
    )


def get_default_custom_fields() -> List[CustomField]:
    """Get the default set of custom fields (migrated from hardcoded fields)."""
    return [
        create_default_timeframe_field(),
        create_default_priority_field(),
        create_default_area_field(),
    ]


def get_field_by_key(fields: List[CustomField], key: str) -> Optional[CustomField]:
    """Find a custom field by its key."""
    for field in fields:
        if field.key == key:
            return field
    return None


def get_visible_fields_sorted(fields: List[CustomField]) -> List[CustomField]:
    """Return only visible fields, sorted by order."""
    visible = [f for f in fields if f.visible]
    return sorted(visible, key=lambda f: f.order)


def normalize_field_order(fields: List[CustomField]) -> List[CustomField]:
    """Normalize field order to be sequential starting from 0."""
    sorted_fields = sorted(fields, key=lambda f: f.order)
    for i, field in enumerate(sorted_fields):
        field.order = i
    return sorted_fields


def generate_field_key(label: str, existing_fields: List[CustomField]) -> str:
    """
    Generate a unique field key from a label.

    Converts label to lowercase, replaces spaces/special chars with underscores,
    and ensures uniqueness by appending a number if needed.

    Returns the generated key.
    """
    import re

    # Convert to lowercase and replace non-alphanumeric chars with underscores
    base_key = re.sub(r'[^a-z0-9]+', '_', label.lower()).strip('_')

    if not base_key:
        base_key = 'field'

    # Check for uniqueness
    key = base_key
    existing_keys = {f.key for f in existing_fields}

    counter = 1
    while key in existing_keys:
        key = f"{base_key}_{counter}"
        counter += 1

    return key


def validate_field_label(label: str) -> tuple[bool, str]:
    """
    Validate a field label.

    Returns (is_valid, error_message).
    """
    if not label or not label.strip():
        return False, "Field label cannot be empty"

    if len(label.strip()) > 50:
        return False, "Field label must be 50 characters or less"

    return True, ""


def get_builtin_fields(visibility: Dict[str, bool]) -> List[CustomField]:
    """
    Get the built-in fields (timeframe, priority, area) with visibility applied.

    Args:
        visibility: Dict mapping field keys to visibility boolean

    Returns:
        List of built-in CustomField objects with visibility set
    """
    timeframe = create_default_timeframe_field()
    timeframe.visible = visibility.get("timeframe", True)

    priority = create_default_priority_field()
    priority.visible = visibility.get("priority", True)

    area = create_default_area_field()
    area.visible = visibility.get("area", True)

    return [timeframe, priority, area]


def get_all_fields(default_visibility: Dict[str, bool], custom_fields: List[CustomField]) -> List[CustomField]:
    """Get all fields (built-in + custom) merged and sorted by order.

    This helper is defensive so it works when called with mocks/partial
    objects in tests. Non-dict visibility or non-list custom fields are
    treated as empty.

    Args:
        default_visibility: Dict mapping built-in field keys to visibility
        custom_fields: List of user-created custom fields

    Returns:
        Complete list of all fields sorted by order
    """
    # Ensure we always work with a real dict for visibility (tests may pass mocks)
    if not isinstance(default_visibility, dict):  # type: ignore[redundant-cast]
        default_visibility = {}

    # Ensure custom_fields is a concrete list (tests may use Mock or None)
    if custom_fields is None:
        custom_list: List[CustomField] = []
    elif isinstance(custom_fields, list):
        custom_list = list(custom_fields)
    else:
        try:
            custom_list = list(custom_fields)  # type: ignore[arg-type]
        except TypeError:
            custom_list = []

    builtin = get_builtin_fields(default_visibility)
    all_fields = builtin + custom_list
    all_fields.sort(key=lambda f: f.order)
    return all_fields
