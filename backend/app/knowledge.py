"""Local business knowledge resolution. No providers, tools, or database writes.

Roles and qualifications are distinct. Legacy prose remains prose, never a
source of verified staff records. Response validation recognizes bounded
grammars over typed relations, rather than trying to prove arbitrary prose.
"""
import hashlib
import re
from collections import defaultdict
from difflib import get_close_matches
from typing import Literal

from pydantic import Field

from .business import BusinessSettings, StaffMember, StrictModel

Interpretation = Literal['exact', 'related', 'ambiguous', 'unmatched']


class KnowledgeDialogue(StrictModel):
    concept: str = ''
    original_wording: str = ''
    source_ids: list[str] = Field(default_factory=list)
    interpretation: Interpretation = 'unmatched'
    used_fallback: bool = False
    failure: Literal['retrieval', 'generation'] | None = None
    fallback_reason: str | None = None
    interrupted: bool = False
    assistant_turn_id: str = ''
    age: int = 0


class StaffFacts(StrictModel):
    staff: list[StaffMember]
    qualification: str | None = None
    interpretation: Interpretation = 'exact'


class KnowledgeMatch(StrictModel):
    concept: str
    interpretation: Interpretation = 'exact'
    source_ids: list[str] = Field(default_factory=list)
    business_topic: str | None = None
    faq_index: int | None = None
    staff_facts: StaffFacts | None = None
    baseline: str | None = None
    missing: bool = False
    repair: bool = False
    repair_query: str | None = None


def normalize(value):
    return re.sub(r"[^\w']+", ' ', value.lower().replace('’', "'")).strip()


def contains(value, phrase):
    return bool(re.search(r'\b' + re.escape(phrase) + r'\b', value))


def canonical_role(value):
    value = normalize(value)
    if value in ('physio', 'physios', 'physiotherapist', 'physiotherapists', 'therapist', 'therapists'):
        return 'physiotherapist'
    if value in ('physician', 'physicians', 'medical doctor', 'medical doctors', 'doctor', 'doctors'):
        return 'physician'
    return value


def qualification(value):
    return 'PhD' if normalize(value) in ('phd', 'ph d', 'doctorate') else value.strip()


def staff_concept(text):
    if re.search(r'\b(phd|ph d|doctorate)\b', text):
        return 'qualification:PhD', 'exact'
    if re.search(r'\b(medical doctors?|physicians?)\b', text):
        return 'role:physician', 'exact'
    if re.search(r'\b(physios?|physiotherapists?|therapists?)\b', text):
        return 'role:physiotherapist', 'exact'
    if re.search(r'\b(doctors?|clinicians?)\b', text):
        return 'staff', 'related'
    if re.search(r'\b(staff|team members?|who works here|who work here|who is working here)\b', text):
        return 'staff', 'exact'
    return None, 'unmatched'


def names_text(names):
    if len(names) < 2:
        return ''.join(names)
    if len(names) == 2:
        return ' and '.join(names)
    return ', '.join(names[:-1]) + ', and ' + names[-1]


def role_label(role, plural):
    # Unknown job titles use "staff members with the role ..." rather than
    # guessing irregular plurals or upgrading a configured role.
    if role in ('physiotherapist', 'physician', 'nurse', 'receptionist'):
        return role + ('s' if plural else '')
    return ('staff members' if plural else 'staff member') + ' with the role ' + role


def staff_groups(facts):
    groups = defaultdict(list)
    for member in facts.staff:
        groups[canonical_role(member.role)].append(member.name)
    return groups


def render_staff(facts):
    if facts.qualification:
        names = names_text([s.name for s in facts.staff])
        return f'{names} {"has" if len(facts.staff) == 1 else "have"} a {facts.qualification}.'
    sentences = []
    for role, names in staff_groups(facts).items():
        label = role_label(role, len(names) > 1)
        if facts.interpretation == 'related':
            sentences.append(f'If you mean our {label}, {"they are" if len(names) > 1 else "that is"} {names_text(names)}.')
        else:
            sentences.append(f'Our {label} {"are" if len(names) > 1 else "is"} {names_text(names)}.')
    return ' '.join(sentences)


def faq_id(entry):
    # Content IDs remain stable across reordering, without migrating old JSON.
    return 'faq:' + hashlib.sha256((entry.question + '\0' + entry.answer).encode()).hexdigest()[:16]


def terms(value):
    words = normalize(value).split()
    vocabulary = ['physiotherapist', 'physiotherapists', 'physiotherapy']
    # Restricted long-word spelling repair; never fuzzy-match names/credentials.
    words = [(get_close_matches(w, vocabulary, n=1, cutoff=.8) or [w])[0]
             if len(w) >= 9 and w.startswith('phy') else w for w in words]
    stop = {'what', 'who', 'which', 'are', 'is', 'the', 'a', 'an', 'do', 'you', 'your',
            'can', 'me', 'tell', 'about', 'here', 'of', 'name', 'names', 'available',
            'please', 'okay', 'so', 'have', 'does'}
    return {canonical_role(w) for w in words if w not in stop}


def rank_faq(text, settings, concept=None):
    query = terms(text)
    scored = []
    for index, entry in enumerate(settings.knowledge):
        # Read both fields for relevance only; never manufacture typed facts.
        topic_text = ' '.join(sorted(terms(entry.question + ' ' + entry.answer)))
        entry_concept, _ = staff_concept(topic_text)
        if concept:
            if concept == 'qualification:PhD' and entry_concept != concept:
                continue
            if concept in ('staff', 'role:physiotherapist') and entry_concept not in ('staff', 'role:physiotherapist'):
                continue
            if concept == 'role:physician':
                continue  # Unverified "doctor" prose cannot establish physician status.
        elif entry_concept:
            continue  # Staff/qualification FAQ must be requested explicitly.
        candidate = terms(entry.question)
        score = len(query & candidate) / max(1, len(query | candidate))
        if concept and entry_concept:
            score = max(score, .6)
        if score >= .3:
            scored.append((score, index))
    scored.sort(reverse=True)
    if not scored:
        return None, False
    if len(scored) > 1 and scored[0][0] - scored[1][0] < .05:
        return None, True
    return scored[0][1], False


def resolve_knowledge(text: str, settings: BusinessSettings,
                      recent: KnowledgeDialogue | None = None) -> KnowledgeMatch | None:
    low = normalize(text)
    repair = bool(re.search(r"\b(don't know|do not know|didn't answer|did not answer|try again|say that again|what about them|who are they|what were their names)\b", low))
    # Only referential repair borrows the previous request, and only briefly.
    # Explicit concepts/new topics always take priority over remembered topics.
    if repair and recent and recent.age <= 1 and recent.original_wording:
        concept, _ = staff_concept(low)
        referential = re.fullmatch(r"(?:okay |so |please )*(?:try again|say that again|what about them|who are they|what were their names|you (?:don't|do not) know(?: about (?:that|them))?)(?: please)?", low)
        if referential and not concept:
            result = resolve_knowledge(recent.original_wording, settings)
            if result:
                result.repair = True
                result.repair_query = recent.original_wording
            return result
    aliases = {
        'cancellation_policy': ('cancellation policy',),
        'hours': ('hours', 'opening', 'open', 'close'),
        'location': ('location', 'address', 'located', 'where are you', 'where is the clinic'),
        'phone': ('phone', 'telephone', 'contact number'),
        'name': ('clinic name', 'business name'),
        'services': ('service', 'services', 'appointments', 'treatments', 'cost', 'price', 'pricing'),
    }
    for topic, words in aliases.items():
        if any(contains(low, word) for word in words):
            # Existing unknown-price behavior is retained when no prices exist.
            if topic == 'services' and re.search(r'\b(cost|price|pricing)\b', low) and not any(s.active and s.price for s in settings.services):
                return KnowledgeMatch(concept='services', missing=True, interpretation='unmatched', repair=repair)
            return KnowledgeMatch(concept=topic, business_topic=topic, source_ids=['settings:' + topic], repair=repair)
    if any(s.active and contains(low, normalize(s.name)) for s in settings.services):
        return KnowledgeMatch(concept='services', business_topic='services', source_ids=['settings:services'], repair=repair)

    concept, interpretation = staff_concept(low)
    # Additional roles and qualifications are matched only against configured data.
    if not concept:
        for member in settings.staff:
            for item in member.qualifications:
                if contains(low, normalize(item)):
                    concept, interpretation = 'qualification:' + qualification(item), 'exact'
                    break
            if concept:
                break
            if contains(low, normalize(member.role)):
                concept, interpretation = 'role:' + canonical_role(member.role), 'exact'
                break
    if concept and settings.staff:
        members = [s for s in settings.staff if s.active]
        requested_qualification = concept.split(':', 1)[1] if concept.startswith('qualification:') else None
        if requested_qualification:
            members = [s for s in members if any(qualification(q).casefold() == requested_qualification.casefold() for q in s.qualifications)]
            requested_role, _ = staff_concept(re.sub(r'\b(phd|ph d|doctorate)\b', '', low))
            if requested_role and requested_role.startswith('role:'):
                members = [s for s in members if canonical_role(s.role) == requested_role.split(':', 1)[1]]
        elif concept.startswith('role:'):
            members = [s for s in members if canonical_role(s.role) == concept.split(':', 1)[1]]
        elif interpretation == 'related':
            # Prefer verified physicians for doctor wording. Otherwise qualify
            # the interpretation and only offer known clinical roles.
            physicians = [s for s in members if canonical_role(s.role) == 'physician']
            if physicians and (contains(low, 'doctor') or contains(low, 'doctors')):
                members, interpretation = physicians, 'exact'
            else:
                members = [s for s in members if canonical_role(s.role) in ('physiotherapist', 'physician', 'nurse')]
        if members:
            facts = StaffFacts(staff=members, qualification=requested_qualification, interpretation=interpretation)
            return KnowledgeMatch(concept=concept, interpretation=interpretation,
                staff_facts=facts, baseline=render_staff(facts), source_ids=['staff:' + s.id for s in members], repair=repair)
        label = 'medical doctors' if concept == 'role:physician' else ('staff with ' + requested_qualification if requested_qualification else 'the requested staff')
        return KnowledgeMatch(concept=concept, missing=True, interpretation='unmatched', repair=repair,
            baseline=f'I do not have configured information about {label}. Would you like to leave a message?')

    index, ambiguous = rank_faq(text, settings, concept)
    if index is not None:
        # Related role wording cannot safely authorize relabeling legacy prose.
        if interpretation == 'related':
            return KnowledgeMatch(concept=concept, interpretation='ambiguous', repair=repair,
                baseline='Do you mean the physiotherapists, or medical doctors?')
        return KnowledgeMatch(concept=concept or 'faq', faq_index=index,
            source_ids=[faq_id(settings.knowledge[index])], repair=repair)
    if ambiguous:
        return KnowledgeMatch(concept=concept or 'faq', interpretation='ambiguous', repair=repair,
            baseline='Could you be more specific about the information you need?')
    if concept or re.search(r'\b(insurance|clinic|parking|qualifications?)\b', low) or low.startswith(('do you have ', 'do you offer ')):
        return KnowledgeMatch(concept=concept or 'faq', missing=True, interpretation='unmatched', repair=repair,
            baseline=('I do not have configured information about medical doctors. Would you like to leave a message?'
                      if concept == 'role:physician' else None))
    return None


def valid_staff_response(reply: str, facts: StaffFacts) -> bool:
    """Match factual clauses with unordered complete name lists.

    Every clause must express one approved relation. No arbitrary trailing
    prose, new entity, stronger role, qualification, or negation is accepted.
    This deliberately favors safe fallback over unrestricted paraphrasing.
    """
    value = reply.strip()
    for prefix in ("Sorry, my last answer wasn't clear. ", 'Sorry, let me clarify. '):
        if value.startswith(prefix):
            value = value[len(prefix):]
    def same_names(value, names):
        # Replace whole names with tokens first, so names containing "and"
        # or punctuation remain intact. Consume each approved name once.
        remaining = value.strip()
        for name in sorted(names, key=len, reverse=True):
            remaining, count = re.subn(r'(?<!\w)' + re.escape(name) + r'(?!\w)', '@', remaining, flags=re.I)
            if count != 1:
                return False
        return bool(re.fullmatch(r'@(?:(?:\s*,\s*(?:and\s+)?|\s+and\s+)@)*', remaining))
    if facts.qualification:
        q = re.escape(facts.qualification)
        patterns = [rf'(.+?) (?:has|have|holds|hold) (?:a |an )?{q}',
                    rf'(?:Our )?staff (?:member|members) with (?:a |an )?{q} (?:is|are) (.+?)']
        for pattern in patterns:
            match = re.fullmatch(pattern + r'\.?', value, re.I)
            if match and same_names(match[1], [s.name for s in facts.staff]):
                return True
        return False
    clauses = re.split(r'\.\s+(?=(?:Our |The |If you mean ))', value)
    groups = staff_groups(facts)
    if len(clauses) != len(groups):
        return False
    used = set()
    for clause in clauses:
        matched = False
        for role, names in groups.items():
            if role in used:
                continue
            label = re.escape(role_label(role, len(names) > 1))
            if facts.interpretation == 'related':
                patterns = [rf'If you mean (?:our |the )?{label},? (?:they are|that is|that would be|their names are) (.+?)',
                            rf'If you mean (?:our |the )?{label},? (.+?) (?:is|are) (?:our |the )?{label}']
            else:
                patterns = [rf'(?:Our |The )?{label} (?:is|are|include|includes) (.+?)',
                            rf'(.+?) (?:is|are) (?:our |the )?{label}']
            for pattern in patterns:
                match = re.fullmatch(pattern + r'\.?', clause, re.I)
                if match and same_names(match[1], names):
                    used.add(role)
                    matched = True
                    break
            if matched:
                break
        if not matched:
            return False
    return True
