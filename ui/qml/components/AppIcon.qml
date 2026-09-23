import QtQuick 2.15

Text {
    property var tokens
    property string glyph: "\uE946"
    text: glyph
    color: tokens ? tokens.textSecondary : "white"
    font.family: tokens ? tokens.iconFamily : "Segoe MDL2 Assets"
    font.pixelSize: 20
    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
    renderType: Text.NativeRendering
}
