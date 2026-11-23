// Precios en vivo desde CoinGecko (API pública, sin key).
// Límite del plan gratuito: ~10-30 llamadas por minuto. No bajar el intervalo
// de refresco por debajo de 60s o CoinGecko bloquea la IP temporalmente.
//
// Caché local: cada respuesta correcta se guarda en localStorage. Si una
// carga posterior falla (red, límite de CoinGecko), el ticker muestra el
// último precio conocido con su antigüedad en vez de desaparecer.

const COINS = "bitcoin,ethereum,solana,binancecoin,ripple,hyperliquid,zcash";

const SYMBOLS = {
    bitcoin: "BTC",
    ethereum: "ETH",
    solana: "SOL",
    binancecoin: "BNB",
    ripple: "XRP",
    hyperliquid: "HYPE",
    zcash: "ZEC"
};

const CACHE_KEY = "bk-precios-cache-v1";

export const getCachedPrices = () => {
    try {
        const raw = localStorage.getItem(CACHE_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (!parsed || !Array.isArray(parsed.prices) || parsed.prices.length === 0) return null;
        if (typeof parsed.savedAt !== "number") return null;
        return parsed;
    } catch {
        return null;
    }
};

export const getPrices = async () => {
    const url = `https://api.coingecko.com/api/v3/simple/price?ids=${COINS}&vs_currencies=usd&include_24hr_change=true`;
    const res = await fetch(url);
    if (!res.ok) throw new Error("CoinGecko respondió " + res.status);
    const data = await res.json();

    const prices = Object.keys(SYMBOLS)
        .filter((id) => data[id])
        .map((id) => ({
            symbol: SYMBOLS[id],
            price: data[id].usd,
            change: data[id].usd_24h_change
        }));

    try {
        localStorage.setItem(CACHE_KEY, JSON.stringify({ prices, savedAt: Date.now() }));
    } catch {
        // Sin almacenamiento (modo privado, cuota llena): el ticker
        // sigue funcionando en la sesión, solo sin caché.
    }
    return prices;
};
