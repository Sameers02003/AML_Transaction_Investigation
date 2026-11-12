from datetime import datetime, timezone
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator, model_validator

class TransactionIn(BaseModel):
    event_id: str = Field(min_length=6, max_length=64)
    source_account_ref: str
    destination_account_ref: str
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(pattern="^INR$")   # single-currency MVP
    channel: str = Field(max_length=20)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def must_be_tz_aware(cls, v):
        if v.tzinfo is None:
            raise ValueError("occurred_at must include a timezone (use UTC, e.g. ...Z)")
        return v.astimezone(timezone.utc)

    @model_validator(mode="after")
    def different_accounts(self):
        if self.source_account_ref == self.destination_account_ref:
            raise ValueError("source and destination must differ")
        return self