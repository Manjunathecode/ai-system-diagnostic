import QtQuick 2.15

QtObject {
    readonly property color canvas: "#071626"
    readonly property color canvasAlt: "#0A1B2D"
    readonly property color sidebar: "#0B1E32"
    readonly property color surface: "#10253A"
    readonly property color surfaceHover: "#15304A"
    readonly property color surfaceRaised: "#18334D"
    readonly property color border: "#28465F"
    readonly property color borderStrong: "#376887"
    readonly property color textPrimary: "#F2F7FC"
    readonly property color textSecondary: "#A9BED2"
    readonly property color textMuted: "#7892AA"
    readonly property color accent: "#2A9BFF"
    readonly property color accentHover: "#4BACFF"
    readonly property color accentSoft: "#153E67"
    readonly property color success: "#35D487"
    readonly property color successSoft: "#123F34"
    readonly property color warning: "#F5B942"
    readonly property color warningSoft: "#4C3916"
    readonly property color danger: "#FF6476"
    readonly property color dangerSoft: "#4A202A"
    readonly property color info: "#65B8FF"

    readonly property int space4: 4
    readonly property int space8: 8
    readonly property int space12: 12
    readonly property int space16: 16
    readonly property int space20: 20
    readonly property int space24: 24
    readonly property int space32: 32
    readonly property int space40: 40
    readonly property int radiusSmall: 8
    readonly property int radiusMedium: 12
    readonly property int radiusLarge: 16
    readonly property int titleSize: 34
    readonly property int headingSize: 22
    readonly property int bodySize: 15
    readonly property int smallSize: 13
    readonly property int animationFast: 120
    readonly property int animationNormal: 220
    readonly property string fontFamily: "Segoe UI Variable Text"
    readonly property string displayFamily: "Segoe UI Variable Display"
    readonly property string iconFamily: "Segoe MDL2 Assets"

    function statusColor(status) {
        var value = String(status || "").toLowerCase()
        if (value === "passed" || value === "healthy" || value === "resolved" || value === "ready") return success
        if (value === "warning" || value === "partially_resolved" || value === "needs attention") return warning
        if (value === "failed" || value === "escalated" || value === "unavailable") return danger
        return textMuted
    }

    function statusSoft(status) {
        var value = String(status || "").toLowerCase()
        if (value === "passed" || value === "healthy" || value === "resolved" || value === "ready") return successSoft
        if (value === "warning" || value === "partially_resolved" || value === "needs attention") return warningSoft
        if (value === "failed" || value === "escalated" || value === "unavailable") return dangerSoft
        return surfaceRaised
    }
}
