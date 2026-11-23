import { useState, useRef, useEffect } from "react";
import { Link } from "react-router-dom";
import { GraduationCap, Send, BookOpen, Sparkles, Trash2, Copy, Check, ArrowRight } from "lucide-react";
import { askTutor } from "../services/tutorService";
import useGlobalReducer from "../hooks/useGlobalReducer";

// Tutor de Block Ethos: responde SOLO con fragmentos de las propias
// lecciones de la plataforma (búsqueda local en el backend, sin IA
// externa). Si el tema no está en las lecciones, lo dice y sugiere
// la lección más cercana.

const SUGERENCIAS = [
    "¿Qué es una blockchain?",
    "¿Qué pasa si pierdo mi frase semilla?",
    "¿Cómo funciona el slashing en Proof of Stake?",
    "¿Para qué sirve require en Solidity?"
];

const MENSAJE_INICIAL = {
    role: "tutor",
    text:
        "Hola, soy el tutor de Block Ethos. Pregúntame sobre lo que enseñan " +
        "las lecciones de la plataforma y te respondo con ese contenido, " +
        "citando la lección de origen. Si algo no está en las lecciones, " +
        "te lo digo en vez de inventarlo.",
    sources: []
};

// Memoria del tutor (2ª tanda, 16 nov 2026): la conversación sobrevive
// al refresco y al cambio de página, guardada solo en este navegador
// (localStorage, nada sale del dispositivo). Clave versionada para
// poder cambiar el formato sin romper lecturas viejas; tope de 30
// mensajes para no crecer sin límite.
const TUTOR_STORAGE_KEY = "bk-tutor-v1";
const TUTOR_MAX_MENSAJES = 30;

const cargarHistorial = () => {
    try {
        const raw = localStorage.getItem(TUTOR_STORAGE_KEY);
        if (!raw) return [MENSAJE_INICIAL];
        const parsed = JSON.parse(raw);
        if (!Array.isArray(parsed) || parsed.length === 0) return [MENSAJE_INICIAL];
        const validos = parsed.filter(
            (m) =>
                m &&
                (m.role === "user" || m.role === "tutor") &&
                typeof m.text === "string" &&
                m.text.length > 0
        );
        return validos.length > 0 ? validos.slice(-TUTOR_MAX_MENSAJES) : [MENSAJE_INICIAL];
    } catch {
        return [MENSAJE_INICIAL];
    }
};

export const Tutor = () => {
    const [messages, setMessages] = useState(cargarHistorial);
    const [input, setInput] = useState("");
    const [sending, setSending] = useState(false);
    const [error, setError] = useState("");
    // Índice del mensaje cuya confirmación «Copiado» está visible.
    const [copiado, setCopiado] = useState(null);
    // Siguiente paso que trae cada respuesta del tutor con sesión
    // (null sin sesión). Vive solo en memoria: al recargar, la
    // tarjeta reaparece con la siguiente pregunta.
    const [siguientePaso, setSiguientePaso] = useState(null);
    const { store } = useGlobalReducer();
    const endRef = useRef(null);
    const primerRender = useRef(true);

    // Guarda cada cambio de la conversación (con tope). El try/catch
    // cubre el modo privado y la cuota llena: sin memoria, el tutor
    // sigue funcionando igual en la sesión.
    useEffect(() => {
        try {
            localStorage.setItem(
                TUTOR_STORAGE_KEY,
                JSON.stringify(messages.slice(-TUTOR_MAX_MENSAJES))
            );
        } catch {
            // Sin almacenamiento disponible: se pierde la memoria
            // entre visitas, pero nada más.
        }
    }, [messages]);

    // Al cargar, el único mensaje es el inicial: no desplazar, porque
    // el scroll llevaba el título bajo el header fijo. Solo se baja
    // al final cuando ya hay conversación (usuario + respuestas).
    // Tampoco se desplaza en el primer render con historial
    // restaurado: el salto inicial escondería el título igual.
    useEffect(() => {
        if (primerRender.current) {
            primerRender.current = false;
            return;
        }
        if (messages.length <= 1) return;
        endRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages, sending]);

    const limpiarConversacion = () => {
        setMessages([MENSAJE_INICIAL]);
        setError("");
    };

    // Copia una respuesta del tutor al portapapeles. La Clipboard API
    // moderna falla sin HTTPS o sin permiso: el fallback con un área
    // de texto temporal cubre esos casos. La confirmación «Copiado»
    // dura 2 s y solo se borra si sigue siendo la última copia.
    const copiarRespuesta = async (texto, i) => {
        try {
            await navigator.clipboard.writeText(texto);
        } catch {
            const area = document.createElement("textarea");
            area.value = texto;
            document.body.appendChild(area);
            area.select();
            document.execCommand("copy");
            document.body.removeChild(area);
        }
        setCopiado(i);
        setTimeout(() => setCopiado((actual) => (actual === i ? null : actual)), 2000);
    };

    const send = async (text) => {
        const question = (text ?? input).trim();
        if (!question || sending) return;
        setError("");
        setInput("");
        setMessages((prev) => [...prev, { role: "user", text: question }]);
        setSending(true);
        try {
            const data = await askTutor(question, store.token);
            setSiguientePaso(data.next_step || null);
            setMessages((prev) => [
                ...prev,
                { role: "tutor", text: data.answer, sources: data.sources || [] }
            ]);
        } catch (e) {
            setError("No se pudo contactar al tutor. Revisa tu conexión e inténtalo de nuevo.");
        } finally {
            setSending(false);
        }
    };

    const handleSubmit = (e) => {
        e.preventDefault();
        send();
    };

    return (
        <div className="container py-5" style={{ maxWidth: "820px" }}>
            <div className="text-center mb-4">
                <p className="bk-eyebrow justify-content-center mb-2">
                    <Sparkles size={16} className="me-1" /> Tutor de la plataforma
                </p>
                <h1 className="fw-bold d-flex align-items-center justify-content-center gap-2">
                    <GraduationCap size={34} /> Pregúntale a las lecciones
                </h1>
                <p className="text-secondary mx-auto" style={{ maxWidth: "620px" }}>
                    Este tutor responde <strong>solo desde las lecciones de Block Ethos</strong>:
                    busca en su contenido y te cita la lección de origen. No usa
                    servicios externos ni inventa respuestas fuera del temario.
                </p>
            </div>

            {siguientePaso && !siguientePaso.all_done && siguientePaso.next_lesson && (
                <div className="card border-0 shadow-sm mb-3 text-white" style={{ background: "var(--bk-grad)" }}>
                    <div className="card-body p-3 d-flex justify-content-between align-items-center flex-wrap gap-2">
                        <div>
                            <span className="badge mb-1" style={{ background: "#fff", color: "#4c1d95" }}>Tu siguiente paso</span>
                            <p className="fw-bold mb-0 text-white">{siguientePaso.next_lesson.lesson_title}</p>
                            <small className="text-white-50">
                                {siguientePaso.next_lesson.path_title} · {siguientePaso.next_lesson.module_title} · {siguientePaso.lessons_completed} de {siguientePaso.lessons_total} lecciones
                            </small>
                            {siguientePaso.quizzes_pending.length > 0 && (
                                <small className="d-block text-white-50">
                                    Quiz pendiente: {siguientePaso.quizzes_pending.map((q) => q.lesson_title).join(", ")}
                                </small>
                            )}
                        </div>
                        <Link
                            to={`/lesson/${siguientePaso.next_lesson.path_id}/${siguientePaso.next_lesson.lesson_id}`}
                            className="btn rounded-pill px-3 fw-semibold d-inline-flex align-items-center gap-2"
                            style={{ background: "#fff", color: "#4c1d95" }}
                        >
                            Continuar <ArrowRight size={16} />
                        </Link>
                    </div>
                </div>
            )}
            {siguientePaso && siguientePaso.all_done && (
                <div className="card border-0 shadow-sm mb-3" style={{ background: "var(--bk-grad)" }}>
                    <div className="card-body p-3 d-flex justify-content-between align-items-center flex-wrap gap-2">
                        <div>
                            <span className="badge mb-1" style={{ background: "#fff", color: "#4c1d95" }}>Ruta completada</span>
                            <p className="fw-bold mb-0 text-white">Terminaste todas las lecciones. ¡A por el certificado!</p>
                        </div>
                        <Link
                            to="/dashboard"
                            className="btn rounded-pill px-3 fw-semibold d-inline-flex align-items-center gap-2"
                            style={{ background: "#fff", color: "#4c1d95" }}
                        >
                            Ir al panel <ArrowRight size={16} />
                        </Link>
                    </div>
                </div>
            )}

            {messages.length > 1 && (
                <div className="d-flex justify-content-end mb-2">
                    <button
                        type="button"
                        className="btn btn-outline-secondary btn-sm rounded-pill d-inline-flex align-items-center gap-1"
                        onClick={limpiarConversacion}
                    >
                        <Trash2 size={14} /> Limpiar conversación
                    </button>
                </div>
            )}

            <div
                className="card border-0 shadow-sm mb-3"
                style={{ maxHeight: "55vh", overflowY: "auto" }}
            >
                <div className="card-body d-flex flex-column gap-3">
                    {messages.map((msg, i) => (
                        <div
                            key={i}
                            className={
                                msg.role === "user"
                                    ? "align-self-end text-end"
                                    : "align-self-start"
                            }
                            style={{ maxWidth: "88%" }}
                        >
                            <div
                                className={
                                    msg.role === "user"
                                        ? "badge text-wrap text-start bg-primary text-white p-3 rounded-4"
                                        : "badge text-wrap text-start bg-body-secondary text-body p-3 rounded-4"
                                }
                                style={{ fontSize: "0.95rem", fontWeight: 400, lineHeight: 1.55 }}
                            >
                                {msg.text}
                            </div>
                            {msg.sources && msg.sources.length > 0 && (
                                <div className="mt-2 text-start">
                                    <span className="small text-secondary d-block mb-1">
                                        <BookOpen size={13} className="me-1" />
                                        Fuentes en las lecciones:
                                    </span>
                                    {msg.sources.map((s, j) => (
                                        <Link
                                            key={j}
                                            to={`/lesson/${s.path_id}/${s.lesson_id}`}
                                            className="d-block small"
                                        >
                                            «{s.lesson_title}» — {s.path_title} · {s.module_title}
                                        </Link>
                                    ))}
                                </div>
                            )}
                            {msg.role === "tutor" && msg.text !== MENSAJE_INICIAL.text && (
                                <button
                                    type="button"
                                    className="btn btn-link btn-sm text-secondary p-0 mt-1 d-inline-flex align-items-center gap-1"
                                    onClick={() => copiarRespuesta(msg.text, i)}
                                >
                                    {copiado === i ? (
                                        <><Check size={13} /> Copiado</>
                                    ) : (
                                        <><Copy size={13} /> Copiar</>
                                    )}
                                </button>
                            )}
                        </div>
                    ))}
                    {sending && (
                        <p className="text-secondary small mb-0" role="status">
                            Buscando en las lecciones…
                        </p>
                    )}
                    <div ref={endRef} />
                </div>
            </div>

            {error && (
                <div className="alert alert-danger py-2" role="alert">
                    {error}
                </div>
            )}

            <div className="d-flex flex-wrap gap-2 mb-3">
                {SUGERENCIAS.map((s) => (
                    <button
                        key={s}
                        type="button"
                        className="btn btn-outline-primary btn-sm rounded-pill"
                        onClick={() => send(s)}
                        disabled={sending}
                    >
                        {s}
                    </button>
                ))}
                {store.token && (
                    <button
                        type="button"
                        className="btn btn-outline-success btn-sm rounded-pill"
                        onClick={() => send("¿Qué me falta para terminar mi ruta?")}
                        disabled={sending}
                    >
                        ¿Qué me falta para terminar mi ruta?
                    </button>
                )}
            </div>

            <form onSubmit={handleSubmit} className="d-flex gap-2">
                <label htmlFor="tutor-input" className="visually-hidden">
                    Tu pregunta sobre las lecciones
                </label>
                <input
                    id="tutor-input"
                    type="text"
                    className="form-control rounded-pill"
                    placeholder="Ej.: ¿qué es la mempool?"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    maxLength={500}
                    disabled={sending}
                />
                <button
                    type="submit"
                    className="btn btn-primary rounded-pill px-4 d-inline-flex align-items-center gap-2"
                    disabled={sending || !input.trim()}
                >
                    <Send size={16} /> Preguntar
                </button>
            </form>
        </div>
    );
};
