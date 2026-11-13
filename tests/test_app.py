import asyncio
from pathlib import Path
from types import SimpleNamespace

from telegram.error import BadRequest

from bot.app import create_application, error_handler, post_init
from bot.handlers import COMMANDS, _quiet_edit
from bot.state import UserState
from common.config import Settings


def test_application_assembly_without_network(sample_db: Path, tmp_path: Path) -> None:
    settings = Settings(
        telegram_bot_token="123456:TEST_TOKEN",
        admin_chat_id=123,
        kirtans_db=sample_db,
        state_dir=tmp_path / "state",
        log_level="INFO",
    )
    application = create_application(settings)
    assert application.bot_data["repository"].meta()["kirtan_count"] == "5"
    assert application.bot_data["user_state"].language(1) == "gu"
    assert application.job_queue is not None
    assert {command for command, _ in COMMANDS} == {
        "start", "search", "k", "lang", "random", "about", "help"
    }


def test_bot_has_no_scraper_imports() -> None:
    bot_root = Path(__file__).parents[1] / "bot"
    for source in bot_root.glob("*.py"):
        assert "from scraper" not in source.read_text()
        assert "import scraper" not in source.read_text()


class FakeBot:
    def __init__(self) -> None:
        self.commands = []
        self.messages = []

    async def set_my_commands(self, commands) -> None:
        self.commands = commands

    async def send_message(self, *args, **kwargs) -> None:
        self.messages.append((args, kwargs))


class FakeQueue:
    def __init__(self) -> None:
        self.job = None

    def run_repeating(self, callback, **kwargs) -> None:
        self.job = (callback, kwargs)


def test_post_init_registers_commands_and_heartbeat_job(tmp_path: Path) -> None:
    bot = FakeBot()
    queue = FakeQueue()
    application = SimpleNamespace(
        bot=bot, job_queue=queue, bot_data={"user_state": UserState(tmp_path)}
    )
    asyncio.run(post_init(application))
    assert [command.command for command in bot.commands] == [name for name, _ in COMMANDS]
    assert queue.job[1]["interval"] == 60
    assert queue.job[1]["name"] == "heartbeat"
    assert (tmp_path / "heartbeat.txt").is_file()


def test_error_alert_is_rate_limited(tmp_path: Path, sample_db: Path) -> None:
    bot = FakeBot()
    settings = Settings("123:TEST", 456, sample_db, tmp_path, "INFO")
    application = SimpleNamespace(bot_data={
        "settings": settings, "last_admin_alert": 0.0,
    })
    context = SimpleNamespace(
        error=RuntimeError("test failure"), application=application, bot=bot,
    )
    asyncio.run(error_handler(None, context))
    asyncio.run(error_handler(None, context))
    assert len(bot.messages) == 1
    assert bot.messages[0][1]["parse_mode"] == "HTML"


def test_not_modified_edit_is_quiet() -> None:
    class Query:
        async def edit_message_text(self, *args, **kwargs):
            raise BadRequest("Message is not modified")

    asyncio.run(_quiet_edit(Query(), "same"))
