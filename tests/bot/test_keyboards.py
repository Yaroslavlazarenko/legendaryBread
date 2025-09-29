# tests/bot/test_keyboards.py

import pytest
from unittest.mock import MagicMock
from app.bot.keyboards import create_paginated_keyboard

# Создаем простые мок-объекты для элементов списка
@pytest.fixture
def mock_items():
    items = []
    for i in range(12): # 12 элементов для 3 страниц при page_size=5
        item = MagicMock()
        item.id = i
        item.__str__ = lambda self, num=i: f"Item {num}"
        items.append(item)
    return items

def test_pagination_empty_list():
    """Тест: если список пуст, возвращается пустая клавиатура (или только extra_buttons)."""
    keyboard = create_paginated_keyboard(items=[])
    assert len(keyboard.inline_keyboard) == 0

    extra_button = [[MagicMock(text="Add")]]
    keyboard_with_extra = create_paginated_keyboard(items=[], extra_buttons=extra_button)
    assert len(keyboard_with_extra.inline_keyboard) == 1
    assert keyboard_with_extra.inline_keyboard[0][0].text == "Add"

def test_pagination_single_page(mock_items):
    """Тест: если все элементы помещаются на одну страницу, кнопок навигации нет."""
    items = mock_items[:3]
    keyboard = create_paginated_keyboard(items=items, page_size=5)
    # Должно быть 3 ряда с элементами, но ни одного ряда с навигацией
    assert len(keyboard.inline_keyboard) == 3
    # Проверяем, что нет кнопок "Назад" или "Вперед"
    callbacks = [btn.callback_data for row in keyboard.inline_keyboard for btn in row]
    assert not any("page_" in cb for cb in callbacks)

def test_pagination_first_page(mock_items):
    """Тест: на первой странице есть кнопка "Вперёд", но нет кнопки "Назад"."""
    keyboard = create_paginated_keyboard(items=mock_items, page=0, page_size=5)
    
    nav_row = keyboard.inline_keyboard[-1] # Навигация всегда последняя
    callbacks = [btn.callback_data for btn in nav_row]

    assert "page_1" in callbacks # Вперед на страницу 1 (вторую)
    assert not any("page_-1" in cb for cb in callbacks) # Назад не должно быть
    assert any("1/3" in btn.text for btn in nav_row) # Проверка счетчика страниц

def test_pagination_middle_page(mock_items):
    """Тест: на средней странице есть обе кнопки навигации."""
    keyboard = create_paginated_keyboard(items=mock_items, page=1, page_size=5)
    
    nav_row = keyboard.inline_keyboard[-1]
    callbacks = [btn.callback_data for btn in nav_row]
    
    assert "page_0" in callbacks # Назад на страницу 0 (первую)
    assert "page_2" in callbacks # Вперед на страницу 2 (третью)
    assert any("2/3" in btn.text for btn in nav_row)

def test_pagination_last_page(mock_items):
    """Тест: на последней странице есть кнопка "Назад", но нет кнопки "Вперёд"."""
    keyboard = create_paginated_keyboard(items=mock_items, page=2, page_size=5)
    
    nav_row = keyboard.inline_keyboard[-1]
    callbacks = [btn.callback_data for btn in nav_row]

    assert "page_1" in callbacks # Назад на страницу 1 (вторую)
    assert not any("page_3" in cb for cb in callbacks) # Вперед не должно быть
    assert any("3/3" in btn.text for btn in nav_row)

def test_pagination_custom_formatters(mock_items):
    """Тест: проверяем работу кастомных форматеров текста и callback_data."""
    keyboard = create_paginated_keyboard(
        items=mock_items[:1],
        button_text_formatter=lambda item: f"Custom Text {item.id}",
        button_callback_formatter=lambda item: f"custom_callback_{item.id}"
    )
    
    item_button = keyboard.inline_keyboard[0][0]
    assert item_button.text == "Custom Text 0"
    assert item_button.callback_data == "custom_callback_0"