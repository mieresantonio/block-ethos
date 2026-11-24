import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowRight } from "lucide-react";

// Lección de muestra (modo invitado, F-BE2): la única lección pública
// sin sesión. No guarda progreso, no enlaza a la siguiente lección ni
// al quiz: al pie, la llamada es registrarse.
const SampleLessonPage = () => {

    const [lesson, setLesson] = useState();
    const [loadError, setLoadError] = useState("");
    const [noSample, setNoSample] = useState(false);
    const lessonSeq = useRef(0);

    const getSample = async () => {
        const seq = ++lessonSeq.current;
        setLoadError("");
        setNoSample(false);
        try {
            const response = await fetch(`${import.meta.env.VITE_BACKEND_URL}/api/lessons/sample`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (response.status === 404) {
                if (seq !== lessonSeq.current) return;
                setNoSample(true);
                return;
            }

            if (!response.ok) {
                throw new Error("No se pudo obtener información");
            }

            const data = await response.json();
            if (seq !== lessonSeq.current) return;
            setLesson(data);

        } catch (error) {
            if (seq !== lessonSeq.current) return;
            setLoadError("No se pudo cargar la lección de muestra. Revisa tu conexión e inténtalo de nuevo.");
        }
    };

    useEffect(() => {
        getSample();
    }, []);

    if (noSample) {
        return (
            <div className="container py-5">
                <h3 className="fw-bold">Todavía no hay lección de muestra</h3>
                <p className="text-secondary">
                    El equipo está preparando la lección de prueba.
                    Mientras tanto, puedes ver las rutas y registrarte gratis.
                </p>
                <div className="d-flex flex-wrap gap-2">
                    <Link to="/courses" className="btn btn-primary rounded-pill px-4">
                        Ver las rutas
                    </Link>
                    <Link to="/register" className="btn btn-outline-primary rounded-pill px-4">
                        Crear cuenta gratis
                    </Link>
                </div>
            </div>
        );
    }

    if (loadError) {
        return (
            <div className="container py-5">
                <div className="alert alert-danger" role="alert">{loadError}</div>
                <div className="d-flex flex-wrap gap-2">
                    <button type="button" className="btn btn-primary rounded-pill px-4" onClick={getSample}>
                        Reintentar
                    </button>
                    <Link to="/courses" className="btn btn-outline-primary rounded-pill px-4">
                        Ver todas las rutas
                    </Link>
                </div>
            </div>
        );
    }

    if (!lesson) {
        return (
            <div className="container py-5 text-center">
                <div className="spinner-border text-primary" role="status">
                    <span className="visually-hidden">Cargando la lección de muestra...</span>
                </div>
            </div>
        );
    }

    return <div className="container mt-4">
        <div className="d-flex flex-wrap gap-2 align-items-center">
            <span className="badge bg-primary-subtle text-primary-emphasis rounded-pill px-3 py-2">
                Lección de muestra
            </span>
            <span className="text-muted small">
                {lesson.path_title} · {lesson.module_title}
            </span>
        </div>
        <h1 className="fw-bold mt-3">{lesson.title}</h1>
        <div className="card border-0 shadow-sm mt-3">
            <div className="card-body p-4 p-md-5">
                {lesson?.content?.trim() ? (
                    <div className="lesson-content">
                        <Markdown remarkPlugins={[remarkGfm]}>{lesson?.content}</Markdown>
                    </div>
                ) : (
                    <p className="text-muted mb-0">
                        Esta lección aún no tiene contenido. Vuelve pronto: el equipo
                        la está preparando.
                    </p>
                )}
            </div>
        </div>
        <div className="card border-0 shadow-sm mt-4 mb-4">
            <div className="card-body p-4 text-center">
                <h4 className="fw-bold">¿Te gustó?</h4>
                <p className="text-muted mb-3">
                    Crea tu cuenta gratis para seguir con la siguiente lección
                    y hacer el quiz, con tu progreso guardado.
                </p>
                <div className="d-flex flex-wrap gap-2 justify-content-center">
                    <Link to="/register" className="btn btn-primary rounded-pill px-4 d-inline-flex align-items-center gap-2">
                        Crear cuenta gratis <ArrowRight size={16} />
                    </Link>
                    <Link to={`/course/${lesson.path_id}`} className="btn btn-outline-primary rounded-pill px-4">
                        Ver la ruta completa
                    </Link>
                </div>
            </div>
        </div>
    </div>;

};

export default SampleLessonPage;
