/*
 * WILDLANDS — Central API Configuration
 */

const WILDLANDS_CONFIG = {
    API_BASE_URL:
        window.WILDLANDS_API_BASE_URL ||
        "http://localhost:8000"
};

const API_BASE_URL = WILDLANDS_CONFIG.API_BASE_URL;

function apiUrl(path) {
    if (!path.startsWith("/")) {
        path = "/" + path;
    }

    return API_BASE_URL.replace(/\/$/, "") + path;
}
