from urllib.parse import parse_qs, quote

from fastapi import Request
from requela import FieldRule, ModelRQLRules, RelationshipRule
from sqlalchemy.sql.selectable import Select

from app.db.models import Account, AccountUser, Actor, Entitlement, Organization, System, User


class ActorRules(ModelRQLRules):
    __model__ = Actor

    id = FieldRule()
    name = FieldRule()
    type = FieldRule()


class TimestampMixin:
    created_at = FieldRule(alias="events.created.at")
    updated_at = FieldRule(alias="events.updated.at")
    deleted_at = FieldRule(alias="events.deleted.at")


class AuditableMixin(TimestampMixin):
    created_by = RelationshipRule(alias="events.created.by", rules=ActorRules())
    updated_by = RelationshipRule(alias="events.updated.by", rules=ActorRules())
    deleted_by = RelationshipRule(alias="events.deleted.by", rules=ActorRules())


class AccountUserRules(ModelRQLRules, AuditableMixin):
    __model__ = AccountUser


class UserRules(ModelRQLRules, AuditableMixin):
    __model__ = User

    id = FieldRule()
    email = FieldRule()
    status = FieldRule()
    accounts = RelationshipRule(rules=AccountUserRules(), alias="accounts")


class AccountRules(ModelRQLRules, AuditableMixin):
    __model__ = Account

    id = FieldRule()
    name = FieldRule()
    external_id = FieldRule()
    type = FieldRule()
    status = FieldRule()


class SystemRules(ModelRQLRules, AuditableMixin):
    __model__ = System

    id = FieldRule()
    external_id = FieldRule()
    owner = RelationshipRule(rules=AccountRules(), alias="owner")
    status = FieldRule()


class OrganizationRules(ModelRQLRules, AuditableMixin):
    __model__ = Organization

    id = FieldRule()
    name = FieldRule()
    currency = FieldRule()
    billing_currency = FieldRule()
    status = FieldRule()


class EntitlementRules(ModelRQLRules, AuditableMixin):
    __model__ = Entitlement

    id = FieldRule()
    name = FieldRule()
    datasource_id = FieldRule()
    status = FieldRule()
    redeemed_by = RelationshipRule(rules=OrganizationRules(), alias="events.redeemed.by")
    terminated_by = RelationshipRule(rules=ActorRules(), alias="events.terminated.by")
    terminated_at = FieldRule(alias="events.terminated.at")


class RQLQuery:
    def __init__(self, rules: ModelRQLRules):
        self.rules = rules

    def __call__(self, request: Request) -> Select | None:
        qs = quote(
            request.scope["query_string"].decode(), safe="/&()=_.-~:,"
        )  # make sure we can decode datetime
        parsed = parse_qs(qs, keep_blank_values=True)
        rql_tokens = [k for k, v in parsed.items() if v == [""]]
        rql_expression = "&".join(rql_tokens)
        if not rql_expression:
            return None
        return self.rules.build_query(rql_expression)
