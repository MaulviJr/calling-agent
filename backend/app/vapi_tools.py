"""Read-only public facts. No conversation interpretation or voice providers."""
from pydantic import Field
from datetime import datetime
from zoneinfo import ZoneInfo

from .business import BusinessSettings, StrictModel
from .database import Business


class BusinessInformationArgs(StrictModel):
    faq_offset: int = Field(default=0, ge=0, le=100, strict=True)
    faq_limit: int = Field(default=5, ge=1, le=10, strict=True)


class StaffInformationArgs(StrictModel):
    offset: int = Field(default=0, ge=0, le=100, strict=True)
    limit: int = Field(default=20, ge=1, le=20, strict=True)


def page(items, offset, limit):
    end = min(offset + limit, len(items))
    return {
        'items': items[offset:end],
        'total': len(items),
        'has_more': end < len(items),
        'next_offset': end if end < len(items) else None,
    }


def get_business_information(settings, args):
    """Whitelist public fields; do not dump operational settings."""
    return {
        'business': {
            'name': settings.name,
            'phone': settings.phone or None,
            'location': settings.location or None,
            'timezone': settings.timezone,
            'current_date': datetime.now(ZoneInfo(settings.timezone)).date().isoformat(),
            'hours': [hour.model_dump(mode='json') for hour in settings.hours],
            'cancellation_policy': settings.cancellation_policy or None,
        },
        'services': [
            {'id': service.id, 'name': service.name,
             'duration_minutes': service.duration, 'price': service.price or None}
            for service in settings.services if service.active
        ],
        'faqs': page([entry.model_dump() for entry in settings.knowledge],
                     args.faq_offset, args.faq_limit),
        'missing_information': 'Null values or missing FAQ answers are unknown, not negative answers.',
    }


def get_staff_information(settings, args):
    members = [
        {'id': member.id, 'name': member.name, 'role': member.role,
         'qualifications': member.qualifications}
        for member in settings.staff if member.active
    ]
    return {
        'staff': page(members, args.offset, args.limit),
        'roles_and_qualifications_are_separate': True,
        'missing_information': (
            'An empty list means no active staff records are supplied. '
            'A qualification does not establish a role. '
            'This directory does not specify who will treat a particular patient.'
        ),
    }


TOOLS = {
    'get_business_information': (BusinessInformationArgs, get_business_information),
    'get_staff_information': (StaffInformationArgs, get_staff_information),
}


def execute_tool(sessions, business_id, name, arguments):
    schema, handler = TOOLS[name]
    args = schema.model_validate(arguments)
    with sessions() as db:
        business = db.get(Business, business_id)
        if business is None:
            return {'success': False, 'status': 'unavailable', 'code': 'information_unavailable'}
        settings = BusinessSettings.model_validate(business.settings)
    return {'success': True, 'status': 'completed', 'data': handler(settings, args)}
