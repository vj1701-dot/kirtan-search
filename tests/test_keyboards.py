from bot.database import KirtanRepository
from bot.keyboards import (
    category_items,
    kirtan_list,
    kirtan_view,
    language_menu,
    main_menu,
    search_results,
)
from bot.models import SearchHit


def all_callback_data(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_every_callback_is_short_and_available_languages_only(repository: KirtanRepository) -> None:
    kirtan = repository.get_kirtan(1)
    search_hit = SearchHit(kirtan.summary, True)
    markups = [
        main_menu(), language_menu(),
        kirtan_view(kirtan, "gu", has_previous=True, has_next=True),
        search_results([search_hit], "abc123", 0, 2),
        category_items(repository.categories("category", offset=0, limit=10), "c", 0, 1),
        kirtan_list([kirtan.summary], "b:c:0", "c:c:1", 0, 1),
    ]
    for markup in markups:
        for callback_data in all_callback_data(markup):
            assert len(callback_data.encode()) <= 64
    language_callbacks = all_callback_data(kirtan_view(kirtan, "gu", has_previous=False, has_next=False))
    assert "k:1:gu" in language_callbacks
    assert "k:1:en_translation" in language_callbacks
    assert "k:1:hi" in language_callbacks
