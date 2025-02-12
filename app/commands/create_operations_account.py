import typer
from rich import print
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Account
from app.enums import AccountStatus, AccountType


def command(
    ctx: typer.Context,
    external_id: str = typer.Argument(..., help="Operation Account external ID"),
):
    """
    Create the SoftwareOne Operations Account.
    """
    db_engine = create_engine(
        str(ctx.obj.postgres_url),
        echo=ctx.obj.debug,
        future=True,
    )
    SessionMaker = sessionmaker(bind=db_engine)
    with SessionMaker() as session:
        query = select(Account).where(
            Account.type == AccountType.OPERATIONS,
            Account.status != AccountStatus.DELETED,
        )
        result = session.execute(query)
        instance = result.scalar_one_or_none()
        if instance:
            print(
                "[orange3]The Operations Account already exist: [/orange3]"
                f"[blue]{instance.id} - {instance.name}[/blue]."
            )
            return

        account = Account(
            name="SoftwareOne",
            type=AccountType.OPERATIONS,
            status=AccountStatus.ACTIVE,
            external_id=external_id,
        )
        session.add(account)
        session.commit()
        session.refresh(account)
        print(
            "[green]The Operations Account has been created: [/green]"
            f"[blue]{account.id} - {account.name}[/blue]."
        )
