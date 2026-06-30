from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class PartnerState:

    connected: bool = False

    authorized: bool = False

    account_id: int | None = None

    balance: float = 0

    equity: float = 0

    margin: float = 0

    free_margin: float = 0

    currency: str = ""

    positions: List = field(default_factory=list)

    symbols: Dict = field(default_factory=dict)


partner_state = PartnerState()
