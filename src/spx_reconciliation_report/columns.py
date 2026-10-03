"""Main Data column definitions and SQL identifier allowlists."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Column:
    label: str
    field: str
    kind: str = "text"


COLUMNS = (
    # Keep identifiers as text so leading zeros from Excel are preserved.
    Column("TO Number", "to_number"), Column("TO High Value", "to_high_value"),
    Column("SPX Tracking Number", "spx_tracking_number"), Column("Order High Value", "order_high_value"),
    Column("TO Status", "to_status"), Column("High Value", "high_value"),
    Column("Sender ID", "sender_id"),
    Column("Sender Name", "sender_name"), Column("Sender Type", "sender_type"),
    Column("Sender Station Type", "sender_station_type"), Column("Receiver ID", "receiver_id"),
    Column("Receiver Name", "receiver_name"), Column("Receiver type", "receiver_type"),
    Column("Receiver Station Type", "receiver_station_type"), Column("Current Station", "current_station"),
    Column("TO Order Quantity", "to_order_quantity", "number"), Column("TO Direction", "to_direction"),
    Column("Weight", "weight", "number"), Column("Length", "length", "number"),
    Column("Width", "width", "number"), Column("Height", "height", "number"),
    Column("Line Hual Trip Number", "line_haul_trip_number"), Column("Operator", "operator"),
    Column("Create Time", "create_time", "date"), Column("Complete Time", "complete_time", "date"),
    Column("Driver", "driver"), Column("Driver Scan Time", "driver_scan_time", "date"),
    Column("Journey Type", "journey_type"), Column("Remark", "remark"),
    Column("Receive Status", "receive_status"), Column("TO Remark", "to_remark"),
    Column("Staging Area ID", "staging_area_id"), Column("Exception Tag", "exception_tag"),
    Column("Packing Method", "packing_method"), Column("Dangerous Goods", "dangerous_goods"),
)
COLUMN_BY_FIELD = {c.field: c for c in COLUMNS}
DEFAULT_FIELDS = [c.field for c in COLUMNS]
SEARCH_FIELDS = [c.field for c in COLUMNS if c.kind == "text"]
