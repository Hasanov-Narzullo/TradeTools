import pytest
from unittest.mock import AsyncMock, patch
from utils import format_portfolio
from api import get_exchange_rate

@pytest.mark.asyncio
async def test_format_empty_portfolio():
    """Тест для пустого портфеля."""
    portfolio = []
    result = await format_portfolio(portfolio)
    assert result == "Портфель пуст."

@pytest.mark.asyncio
@patch("api.get_exchange_rate", AsyncMock(return_value=90.0))  # Мокаем курс USD/RUB
async def test_format_portfolio_with_assets():
    """Тест для портфеля с активами."""
    portfolio = [
        {
            'symbol': 'AAPL',
            'asset_type': 'stock',
            'amount': 10.0,
            'purchase_price': 150.0,
            'current_price': 170.0
        },
        {
            'symbol': 'BTC',
            'asset_type': 'crypto',
            'amount': 1.0,
            'purchase_price': 40000.0,
            'current_price': 45000.0
        }
    ]
    result = await format_portfolio(portfolio)

    # Проверяем, что в результате есть информация об активах
    assert "AAPL (Акция)" in result
    assert "BTC (Криптовалюта)" in result

    # Проверяем итоговые суммы
    total_invested_usd = 10 * 150 + 1 * 40000  # 41500 USD
    total_invested_rub = total_invested_usd * 90  # 3735000 RUB
    total_value_usd = 10 * 170 + 1 * 45000  # 46700 USD
    total_value_rub = total_value_usd * 90  # 4203000 RUB

    assert f"Сумма вложений: {total_invested_rub:.2f} руб | ${total_invested_usd:.2f}" in result
    assert f"Текущая стоимость портфеля: {total_value_rub:.2f} руб | ${total_value_usd:.2f}" in result

    # Проверяем суммы по типам активов
    stocks_invested_rub = 10 * 150 * 90  # 135000 RUB
    stocks_value_rub = 10 * 170 * 90  # 153000 RUB
    crypto_invested_rub = 1 * 40000 * 90  # 3600000 RUB
    crypto_value_rub = 1 * 45000 * 90  # 4050000 RUB

    assert f"Текущая стоимость акций: {stocks_value_rub:.2f} руб | ${10 * 170:.2f}" in result
    assert f"Текущая стоимость криптовалют: {crypto_value_rub:.2f} руб | ${1 * 45000:.2f}" in result

@pytest.mark.asyncio
@patch("api.get_exchange_rate", AsyncMock(side_effect=Exception("API недоступен")))
async def test_format_portfolio_exchange_rate_fallback():
    """Тест для проверки работы с фиксированным курсом при сбое API."""
    portfolio = [
        {
            'symbol': 'AAPL',
            'asset_type': 'stock',
            'amount': 10.0,
            'purchase_price': 150.0,
            'current_price': 170.0
        }
    ]
    result = await format_portfolio(portfolio)

    # Проверяем, что используется фиксированный курс (90.0)
    total_invested_rub = 10 * 150 * 90  # 135000 RUB
    total_value_rub = 10 * 170 * 90  # 153000 RUB
    assert f"Сумма вложений: {total_invested_rub:.2f} руб | ${10 * 150:.2f}" in result
    assert f"Текущая стоимость портфеля: {total_value_rub:.2f} руб | ${10 * 170:.2f}" in result