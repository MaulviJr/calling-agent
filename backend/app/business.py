from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Service(StrictModel):
    id: str = Field(pattern=r'^[a-z0-9_-]{1,40}$')
    name: str = Field(min_length=1, max_length=100)
    duration: int = Field(default=30, ge=5, le=240)
    active: bool = True
    price: str = Field(default='', max_length=100)


class Hours(StrictModel):
    weekday: int = Field(ge=0, le=6)
    opens: time
    closes: time

    @model_validator(mode='after')
    def order(self):
        if self.opens >= self.closes:
            raise ValueError('Opening time must precede closing time; split overnight hours.')
        return self


class Knowledge(StrictModel):
    question: str = Field(min_length=1, max_length=200)
    answer: str = Field(min_length=1, max_length=2000)


class StaffMember(StrictModel):
    id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,64}$')
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=100)
    qualifications: list[str] = Field(default_factory=list, max_length=20)
    active: bool = True

    @field_validator('qualifications')
    @classmethod
    def clean_qualifications(cls, values):
        cleaned = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if any(len(value) > 100 for value in cleaned):
            raise ValueError('Qualifications must be at most 100 characters.')
        return cleaned


class BusinessSettings(StrictModel):
    name: str = Field(default='Your clinic', min_length=1, max_length=100)
    timezone: str = 'UTC'
    phone: str = Field(default='', max_length=50)
    location: str = Field(default='', max_length=500)
    assistant_name: str = Field(default='Ava', max_length=50)
    greeting: str = Field(default='Hello, how can I help you today?', max_length=300)
    escalation_number: str = Field(default='', max_length=50)
    voice_id: str = Field(default='', max_length=100)
    buffer_minutes: int = Field(default=0, ge=0, le=120)
    minimum_notice_minutes: int = Field(default=60, ge=0, le=43200)
    maximum_advance_days: int = Field(default=90, ge=1, le=365)
    require_email: bool = False
    services: list[Service] = Field(default_factory=list, max_length=50)
    hours: list[Hours] = Field(default_factory=list, max_length=7)
    knowledge: list[Knowledge] = Field(default_factory=list, max_length=100)
    staff: list[StaffMember] = Field(default_factory=list, max_length=100)
    escalation_keywords: list[str] = Field(default_factory=lambda: ['human', 'complaint'], max_length=30)
    after_hours_message: str = Field(default='The team will follow up during business hours.', max_length=500)
    cancellation_policy: str = Field(default='', max_length=2000)

    @field_validator('timezone')
    @classmethod
    def timezone_exists(cls, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError('Use a valid IANA timezone, such as Asia/Karachi.')
        return value

    @model_validator(mode='after')
    def unique(self):
        if len({s.id for s in self.staff}) != len(self.staff):
            raise ValueError('Staff IDs must be unique.')
        if len({s.id for s in self.services}) != len(self.services):
            raise ValueError('Service IDs must be unique.')
        if len({h.weekday for h in self.hours}) != len(self.hours):
            raise ValueError('Use one opening interval per weekday.')
        return self
