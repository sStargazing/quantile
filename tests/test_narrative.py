from app.config.destinations import get_destination, get_home_currency, get_period
from app.services.narrative import explanation, headline

AUD, JAPAN, UAE = get_home_currency("AUD"), get_destination("japan"), get_destination("uae")
FIVE_YEARS, ONE_YEAR = get_period("5y"), get_period("1y")


def test_headline_adapts_to_inputs_and_rounds_down():
    assert headline(AUD, JAPAN, FIVE_YEARS, 87.9, 0.0) == "1 AUD buys more JPY today than on 87% of days in the past 5 years."
    usd = get_home_currency("USD")
    assert headline(usd, JAPAN, ONE_YEAR, 12.0, 0.0) == "1 USD buys more JPY today than on 12% of days in the past year."


def test_headline_for_best_day_and_pegged_currency():
    assert headline(AUD, JAPAN, FIVE_YEARS, 100.0, 0.0).endswith("than on any other day in the past 5 years.")
    usd = get_home_currency("USD")
    assert headline(usd, UAE, ONE_YEAR, 0.0, 97.3) == "1 USD buys the same amount of AED today as on 97% of days in the past year."


def test_explanation_mentions_inflation_only_when_material():
    text = explanation(AUD, JAPAN, FIVE_YEARS, 88.2, 0.0, 15.8, 2.3)
    assert "better than on 88% of days" in text
    assert "goes 15.8% further than its 5-year average" in text
    assert "Slower price rises in Japan than in Australia add 2.3 points" in text
    quiet = explanation(AUD, JAPAN, FIVE_YEARS, 50.0, 0.0, -3.0, 0.5)
    assert "3.0% less far" in quiet and "price rises" not in quiet


def test_country_names_read_naturally_mid_sentence():
    gbp = get_home_currency("GBP")
    assert "than in the United Kingdom" in explanation(gbp, JAPAN, FIVE_YEARS, 90.0, 0.0, 30.0, 10.0)
    eur = get_home_currency("EUR")
    assert "than in the eurozone" in explanation(eur, JAPAN, FIVE_YEARS, 90.0, 0.0, 30.0, 10.0)
