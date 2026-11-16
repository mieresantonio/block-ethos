import { useEffect, useState } from "react";
import useGlobalReducer from "../hooks/useGlobalReducer";
import LearningPathCard from "./LearningPathCard";
import { PathSkeletonGrid } from "./PathCardSkeleton";
import { LoadError, BACKEND_DORMIDO } from "./LoadError";
import { Link } from "react-router-dom";

const LearningPaths = () => {

    const { store, dispatch } = useGlobalReducer();
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);

    const getLearningPaths = async () => {
        setLoading(true);
        setError(false);
        try {
            const response = await fetch(`${import.meta.env.VITE_BACKEND_URL}/api/learning-paths`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            dispatch({ type: "set_learning_paths", payload: data });
        } catch (err) {
            // El detalle técnico queda en la consola; el visitante ve
            // un mensaje humano con Reintentar (antes el fallo era
            // silencioso y la sección quedaba vacía sin explicación).
            // eslint-disable-next-line no-console -- diagnóstico para quien desarrolla, no para el visitante
            console.error("No se pudieron cargar las rutas:", err);
            setError(true);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        getLearningPaths();
    }, []);

    // Si el store ya trae rutas (vuelta desde otra página), se muestran
    // de inmediato y la recarga corre en segundo plano: ni esqueleto
    // ni error tapan contenido que ya tenemos.
    const hasPaths = (store.learningPaths?.length ?? 0) > 0;

    return <div className="container py-5">
        <div className="row text-center mb-4">
            <span className="bk-eyebrow justify-content-center mb-2">Catálogo educativo Web3</span>
            <h3 className="fw-bold">Rutas de <span className="gradient-heading">Aprendizaje</span></h3>
        </div>
        {loading && !hasPaths && (
            <>
                <span className="visually-hidden" role="status">Cargando rutas de aprendizaje...</span>
                <PathSkeletonGrid count={3} />
            </>
        )}
        {error && !hasPaths && (
            <LoadError
                title={BACKEND_DORMIDO.title}
                message={BACKEND_DORMIDO.message}
                onRetry={getLearningPaths}
            />
        )}
        {!loading && !error && !hasPaths && (
            <p className="text-muted text-center pb-4">
                Todavía no hay rutas publicadas.
            </p>
        )}
        {hasPaths && (
            <div className="row g-4 pb-5">
                {store.learningPaths?.map((value, index) => {
                    return <div key={value.id} className="col-12 col-md-6 col-lg-4">
                        <LearningPathCard data={value} />
                    </div>;
                })}
            </div>
        )}
        <div className="row">
            <div className="col-12 text-center pb-2">
                <Link to="/courses" className="btn btn-outline-primary rounded-pill px-4">
                    Ver todas las rutas
                </Link>
            </div>
        </div>
    </div>;
};

export default LearningPaths;
