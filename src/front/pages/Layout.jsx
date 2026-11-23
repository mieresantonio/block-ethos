import { Outlet, useLocation } from "react-router-dom/dist";
import ScrollToTop from "../components/ScrollToTop";
import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";

// Base component that maintains the navbar and footer throughout the page and the scroll to top functionality.
export const Layout = () => {
    const location = useLocation();
    return (
        <ScrollToTop location={location}>
            <div className="bk-layout">
                {/* Enlace de salto: quien navega con teclado llega al
                    contenido sin pasar por toda la barra de navegación. */}
                <a href="#contenido" className="bk-skip-link">
                    Saltar al contenido principal
                </a>
                <Navbar />
                <main id="contenido" className="bk-main" tabIndex="-1">
                    <Outlet />
                </main>
                <Footer />
            </div>
        </ScrollToTop>
    );
}; 