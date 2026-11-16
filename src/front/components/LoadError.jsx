import PropTypes from "prop-types";
import { WifiOff } from "lucide-react";

// Estado de error humano al cargar datos del backend: nunca muestra
// el mensaje técnico crudo al visitante (antes se veía literalmente
// «Failed to fetch» en inglés). El detalle técnico queda en la
// consola del navegador, donde lo puede ver quien desarrolla.
export const LoadError = ({ title, message, onRetry }) => (
    <div className="card border-0 shadow-sm p-4 text-center my-4" role="alert">
        {/* align-self-center: .card es flex-column en Bootstrap, así que
            text-center no centra el icono; sin esto quedaba a la izquierda. */}
        <span className="icon-chip align-self-center mb-3"><WifiOff size={22} /></span>
        <h5 className="fw-bold">{title}</h5>
        <p className="text-muted small mx-auto mb-3" style={{ maxWidth: "480px" }}>
            {message}
        </p>
        <div>
            <button type="button" className="btn btn-primary rounded-pill px-4" onClick={onRetry}>
                Reintentar
            </button>
        </div>
    </div>
);

LoadError.propTypes = {
    title: PropTypes.string.isRequired,
    message: PropTypes.string.isRequired,
    onRetry: PropTypes.func.isRequired
};

// Mensaje compartido: el backend vive en un plan gratuito que duerme
// cuando nadie lo usa; la primera carga en frío tarda unos segundos.
export const BACKEND_DORMIDO = {
    title: "El servidor está despertando",
    message: "Nuestro servidor duerme cuando nadie lo usa y tarda unos segundos en arrancar. Pulsa «Reintentar» y el contenido aparecerá."
};
