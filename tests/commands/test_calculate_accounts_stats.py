from sqlalchemy.ext.asyncio import AsyncSession

from app.commands.calculate_accounts_stats import calculate_accounts_stats
from app.conf import Settings
from app.enums import AccountStatus, EntitlementStatus


async def test_stats(
    test_settings: Settings,
    db_session: AsyncSession,
    entitlement_factory,
    account_factory,
):
    active_account = await account_factory(status=AccountStatus.ACTIVE)
    num = {EntitlementStatus.ACTIVE: 30, EntitlementStatus.NEW: 15, EntitlementStatus.TERMINATED: 7}

    for status, how_many in num.items():
        for _ in range(how_many):
            await entitlement_factory(
                owner=active_account,
                status=status,
            )

    await calculate_accounts_stats(test_settings)
    await db_session.refresh(active_account)
    assert active_account.status == AccountStatus.ACTIVE
    assert active_account.active_entitlements_count == 30
    assert active_account.new_entitlements_count == 15
    assert active_account.terminated_entitlements_count == 7
