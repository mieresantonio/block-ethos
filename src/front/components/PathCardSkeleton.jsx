import PropTypes from "prop-types";

// Esqueleto de tarjeta de ruta de aprendizaje: misma silueta que
// CourseCard / LearningPathCard (imagen de 160 px, badge, título,
// descripción y pie) para que la carga no mueva el layout al llegar
// los datos reales. El brillo animado vive en .bk-skeleton (index.css).
export const PathCardSkeleton = () => (
    <div className="card h-100 overflow-hidden" aria-hidden="true">
        <div className="bk-skeleton bk-skeleton-img" />
        <div className="card-body d-flex flex-column">
            <div className="bk-skeleton mb-2" style={{ width: "92px", height: "20px" }} />
            <div className="bk-skeleton mb-2" style={{ width: "80%", height: "22px" }} />
            <div className="bk-skeleton mb-2" style={{ width: "100%", height: "14px" }} />
            <div className="bk-skeleton mb-3" style={{ width: "65%", height: "14px" }} />
            <div className="d-flex justify-content-between align-items-center mt-auto">
                <div className="bk-skeleton" style={{ width: "70px", height: "14px" }} />
                <div className="bk-skeleton" style={{ width: "96px", height: "31px", borderRadius: "50rem" }} />
            </div>
        </div>
    </div>
);

// Grilla de esqueletos con la misma distribución responsive que las
// grillas de rutas (1 / 2 / 3 columnas).
export const PathSkeletonGrid = ({ count = 6 }) => (
    <div className="row g-4 mb-5">
        {Array.from({ length: count }).map((_, i) => (
            <div className="col-12 col-md-6 col-lg-4" key={i}>
                <PathCardSkeleton />
            </div>
        ))}
    </div>
);

PathSkeletonGrid.propTypes = {
    count: PropTypes.number
};
