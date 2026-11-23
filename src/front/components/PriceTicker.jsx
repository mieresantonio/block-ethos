import { useState, useEffect } from "react";
import { getPrices, getCachedPrices } from "../services/pricesService.js";

// Ticker de precios: en vivo desde CoinGecko, con el último precio
// conocido en caché si la carga falla (se indica su antigüedad).
// Sin precios vivos ni caché, no se muestra nada: mejor ausente
// que inventado.

export const PriceTicker = () => {
    const [precios, setPrecios] = useState([]);
    const [cacheMinutos, setCacheMinutos] = useState(null);

    useEffect(() => {
        let activo = true;
        const cargar = () => {
            getPrices()
                .then((data) => {
                    if (!activo) return;
                    setPrecios(data);
                    setCacheMinutos(null);
                })
                .catch(() => {
                    if (!activo) return;
                    const cache = getCachedPrices();
                    if (cache) {
                        setPrecios(cache.prices);
                        setCacheMinutos(Math.max(1, Math.round((Date.now() - cache.savedAt) / 60000)));
                    }
                });
        };

        cargar();
        const intervalo = setInterval(cargar, 60000);
        return () => { activo = false; clearInterval(intervalo); };
    }, []);

    if (precios.length === 0) return null;

    // Se duplica la lista para que el bucle se vea continuo
    const lista = [...precios, ...precios];

    return (
        <div className="overflow-hidden py-2 border-bottom" style={{ backgroundColor: "rgba(5,8,15,.85)" }}>
            <div className="d-flex ticker-track" style={{ width: "max-content" }} aria-hidden="true">
                {lista.map((coin, i) => (
                    <div key={i} className="d-flex align-items-center px-4 text-white small">
                        <span className="fw-bold me-2">{coin.symbol}</span>
                        <span className="me-2">
                            ${coin.price.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                        </span>
                        <span className={coin.change >= 0 ? "text-success" : "text-danger"}>
                            {coin.change >= 0 ? "▲" : "▼"} {Math.abs(coin.change).toFixed(2)}%
                        </span>
                    </div>
                ))}
            </div>
            {cacheMinutos !== null && (
                <p className="text-center text-secondary mb-0 mt-1" style={{ fontSize: "0.72rem" }}>
                    Precios en caché · actualizados hace {cacheMinutos} min
                </p>
            )}
        </div>
    );
};
