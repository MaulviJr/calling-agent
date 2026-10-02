"""Action proposals are data; only the controller may execute them."""
from typing import Literal
from pydantic import Field
from backend.app.business import StrictModel


class AgentDecision(StrictModel):
    action: Literal['book','confirm','faq','message','human','cancel','reschedule','emergency','medical','greeting','capabilities','conversation','clarify','out_of_scope','unknown']='unknown'
    conversational_goal: str = Field(default='', max_length=200)
    needs_business_knowledge: bool = False
    direct_conversation: bool = False
    conversation_topic: Literal['hearing','identity','previous_turn','interruption','wellbeing','general'] | None = None
    caller_name: str | None = Field(default=None,max_length=120)
    phone: str | None = Field(default=None,max_length=50)
    email: str | None = Field(default=None,max_length=254)
    service_id: str | None = Field(default=None,max_length=40)
    date_phrase: str | None = Field(default=None,max_length=80)
    time_phrase: str | None = Field(default=None,max_length=80)
    selected_slot: str | None = Field(default=None,max_length=80)
    appointment_id: str | None = Field(default=None,max_length=32)
    faq_index: int | None = Field(default=None,ge=0)
    business_topic: Literal['name','phone','location','hours','services','cancellation_policy'] | None = None
    message_text: str | None = Field(default=None,max_length=2000)


