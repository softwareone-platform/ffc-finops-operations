import random

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.commands.calculate_accounts_stats import calculate_accounts_stats
from app.conf import Settings
from app.db.models import Account, AccountUser, User
from app.enums import AccountStatus, AccountType, EntitlementStatus
from tests.types import ModelFactory


async def test_stats(
    test_settings: Settings,
    db_session: AsyncSession,
    operations_account: Account,
    operations_client: AsyncClient,
    user_factory: ModelFactory[User],
    accountuser_factory: ModelFactory[AccountUser],
    affiliate_account,
    entitlement_factory,
    account_factory,
):
    status_options = [EntitlementStatus.NEW, EntitlementStatus.ACTIVE, EntitlementStatus.TERMINATED]
    account_type = [AccountType.AFFILIATE, AccountType.OPERATIONS]

    for index in range(16):
        for _ in range(int(16 / 4)):
            active_account = await account_factory(
                status=AccountStatus.ACTIVE,
                name=f"TEST_ACCOUNT_{index}",
                type=account_type[random.randint(0, len(account_type) - 1)],
            )
            await entitlement_factory(
                name="AWS",
                affiliate_external_id=f"EXTERNAL_ID_{index}",
                datasource_id=f"CONTAINER_ID_{index}",
                owner=active_account,
                status=status_options[random.randint(0, len(status_options) - 1)],
            )
    await calculate_accounts_stats(test_settings)
