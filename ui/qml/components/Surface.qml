import QtQuick 2.15

Rectangle {
    property var tokens
    color: tokens.surface
    border.color: tokens.border
    border.width: 1
    radius: tokens.radiusMedium
}
