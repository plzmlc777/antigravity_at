export const APP_VERSION = "v1.8.0";
export const COMMIT_HASH = "75bbf2a";
export const BUILD_DATE = new Date().toISOString().split('T')[0];

const MOUNTAINS = [
    "Namsan (262m)",        // v1.0
    "Achasan (295m)",       // v1.1
    "Inwangsan (338m)",     // v1.2
    "Buramsan (508m)",      // v1.3
    "Cheonggyesan (582m)",  // v1.4
    "Gwanaksan (632m)",     // v1.5
    "Suraksan (638m)",      // v1.6
    "Dobongsan (740m)",     // v1.7
    "Bukhansan (836m)",     // v1.8 (Current)
    "Unaksan (935m)",       // v1.9
    "Chiaksan (1,288m)",    // v1.10
    "Odaesan (1,563m)",     // v1.11
    "Deogyusan (1,614m)",   // v1.12
    "Seoraksan (1,708m)",   // v1.13
    "Jirisan (1,915m)",     // v1.14
    "Hallasan (1,947m)",    // v1.15
    "Baekdusan (2,744m)",   // v1.16
    "Fuji (3,776m)"         // v1.17
];

export const getCodeName = () => {
    try {
        // Parse "v1.8.0" -> 8
        const minor = parseInt(APP_VERSION.split('.')[1]);
        if (minor >= 0 && minor < MOUNTAINS.length) {
            return MOUNTAINS[minor];
        }
        return "Unknown Peak";
    } catch (e) {
        return "Base Camp";
    }
};

export const CODE_NAME = getCodeName();
