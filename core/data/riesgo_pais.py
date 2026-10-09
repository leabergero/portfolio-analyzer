"""Prima de riesgo país (CRP) por país, en puntos porcentuales anuales.

Es la tabla de Aswath Damodaran (NYU Stern), versión de enero de 2026
(pages.stern.nyu.edu/~adamodar → Country Risk Premiums): el spread de default
del soberano, por calificación, escalado por cuánto más volátil es la bolsa que
el bono. Es lo que un inversor le pide de más a una acción de ese país sobre la
prima de un mercado maduro; el Monte Carlo la suma al CAPM (ver
`core/models/montecarlo.py`).

ponytail: tabla fija, se actualiza a mano una vez por año cuando Damodaran
publica la de enero (el backtest de 2026-10 usó una por año desde 2005, sin
mirar el futuro, y midió que sumarla mejora el pronóstico). Leerla en vivo no
vale la pena: cambia una vez al año.
"""

CRP = {
    "Abu Dhabi": 0.64,
    "Albania": 4.66,
    "Andorra (Principality of)": 2.07,
    "Angola": 8.41,
    "Argentina": 9.71,
    "Armenia": 4.66,
    "Aruba": 2.85,
    "Australia": 0,
    "Austria": 0.36,
    "Azerbaijan": 2.85,
    "Bahamas": 5.83,
    "Bahrain": 7.12,
    "Bangladesh": 7.12,
    "Barbados": 7.12,
    "Belarus": 26.66,
    "Belgium": 0.78,
    "Belize": 9.71,
    "Benin": 5.83,
    "Bermuda": 1.1,
    "Bolivia": 15.54,
    "Bosnia and Herzegovina": 8.41,
    "Botswana": 2.07,
    "Brazil": 3.24,
    "Bulgaria": 2.07,
    "Burkina Faso": 9.71,
    "Cambodia": 7.12,
    "Cameroon": 9.71,
    "Canada": 0,
    "Cape Verde": 7.12,
    "Cayman Islands": 0.78,
    "Chile": 1.1,
    "China": 0.91,
    "Colombia": 2.85,
    "Congo (Democratic Republic of)": 8.41,
    "Congo (Republic of)": 11.66,
    "Cook Islands": 5.83,
    "Costa Rica": 3.9,
    "Croatia": 1.55,
    "Cuba": 15.54,
    "Curacao": 2.85,
    "Cyprus": 1.55,
    "Czech Republic": 0.78,
    "Côte d'Ivoire": 3.9,
    "Denmark": 0,
    "Dominican Republic": 3.9,
    "Ecuador": 12.95,
    "Egypt": 9.71,
    "El Salvador": 8.41,
    "Estonia": 0.91,
    "Ethiopia": 11.66,
    "Fiji": 5.83,
    "Finland": 0.36,
    "France": 0.78,
    "Gabon": 11.66,
    "Georgia": 3.9,
    "Germany": 0,
    "Ghana": 9.71,
    "Greece": 2.85,
    "Guatemala": 3.24,
    "Guernsey (States of)": 0.91,
    "Honduras": 5.83,
    "Hong Kong": 0.78,
    "Hungary": 2.46,
    "Iceland": 0.91,
    "India": 2.85,
    "Indonesia": 2.46,
    "Iraq": 9.71,
    "Ireland": 0.78,
    "Isle of Man": 0.78,
    "Israel": 2.07,
    "Italy": 2.46,
    "Jamaica": 4.66,
    "Japan": 0.91,
    "Jersey (States of)": 0.78,
    "Jordan": 4.66,
    "Kazakhstan": 2.07,
    "Kenya": 8.41,
    "Korea": 0.64,
    "Kuwait": 0.91,
    "Kyrgyzstan": 8.41,
    "Laos": 11.66,
    "Latvia": 1.55,
    "Lebanon": 26.66,
    "Liechtenstein": 0,
    "Lithuania": 1.1,
    "Luxembourg": 0,
    "Macao": 0.78,
    "Macedonia": 4.66,
    "Malaysia": 1.55,
    "Maldives": 11.66,
    "Mali": 11.66,
    "Malta": 1.1,
    "Mauritius": 2.85,
    "Mexico": 2.46,
    "Moldova": 8.41,
    "Mongolia": 5.83,
    "Montenegro": 5.83,
    "Montserrat": 2.85,
    "Morocco": 3.24,
    "Mozambique": 12.95,
    "Namibia": 5.83,
    "Nepal": 4.66,
    "Netherlands": 0,
    "New Zealand": 0,
    "Nicaragua": 7.12,
    "Niger": 12.95,
    "Nigeria": 8.41,
    "Norway": 0,
    "Oman": 2.85,
    "Pakistan": 9.71,
    "Panama": 2.85,
    "Papua New Guinea": 7.12,
    "Paraguay": 2.85,
    "Peru": 2.07,
    "Philippines": 2.46,
    "Poland": 1.1,
    "Portugal": 1.55,
    "Qatar": 0.64,
    "Ras Al Khaimah (Emirate of)": 1.55,
    "Romania": 2.85,
    "Rwanda": 7.12,
    "Saudi Arabia": 0.78,
    "Senegal": 9.71,
    "Serbia": 3.9,
    "Sharjah": 3.24,
    "Singapore": 0,
    "Slovakia": 1.55,
    "Slovenia": 1.55,
    "Solomon Islands": 9.71,
    "South Africa": 3.9,
    "Spain": 1.55,
    "Sri Lanka": 15.54,
    "St. Maarten": 3.9,
    "St. Vincent & the Grenadines": 8.41,
    "Suriname": 9.71,
    "Swaziland": 7.12,
    "Sweden": 0,
    "Switzerland": 0,
    "Taiwan": 0.78,
    "Tajikistan": 8.41,
    "Tanzania": 5.83,
    "Thailand": 2.07,
    "Togo": 8.41,
    "Trinidad and Tobago": 3.9,
    "Tunisia": 9.71,
    "Turkey": 4.66,
    "Turks and Caicos Islands": 2.07,
    "Uganda": 8.41,
    "Ukraine": 15.54,
    "United Arab Emirates": 0.64,
    "United Kingdom": 0.78,
    "United States": 0.23,
    "Uruguay": 2.07,
    "Uzbekistan": 4.66,
    "Venezuela": 26.66,
    "Vietnam": 3.9,
    "Zambia": 11.66,}

# yfinance y la tabla de países ETF (`composicion.PAISES_ETF`) no siempre usan
# el nombre de Damodaran.
_ALIAS = {"South Korea": "Korea"}
_EUROPA = ("Germany", "France", "Netherlands", "Spain", "Italy")
_REGIONES = {
    "Europe": sum(CRP[p] for p in _EUROPA) / len(_EUROPA),
    "Eurozone": sum(CRP[p] for p in _EUROPA) / len(_EUROPA),
    "World": 0.0, "Developed Markets ex-US": 0.0,
}


# σ de la bolsa / σ del bono soberano que Damodaran usa para pasar del spread
# de default a la prima de acciones (enero 2026: 9,71 / 6,37 en Argentina).
_VOL_RELATIVA = 1.52


def spread_default(pais) -> float:
    """Lo que un bono en dólares de ese país paga sobre la tasa libre por el
    riesgo de default: la prima de acciones sin el escalado por volatilidad."""
    return prima(pais) / _VOL_RELATIVA


def prima(pais) -> float:
    """CRP anual en fracción (0,097 = 9,7 %). `pais` puede ser un nombre o una
    mezcla por ingresos {país: peso}. Un país que no está en la tabla —o una
    región emergente, que no es un soberano— no suma prima.
    """
    if isinstance(pais, dict):
        return sum(w * prima(p) for p, w in pais.items())
    pais = _ALIAS.get(pais, pais)
    return (CRP.get(pais) if pais in CRP else _REGIONES.get(pais, 0.0)) / 100
