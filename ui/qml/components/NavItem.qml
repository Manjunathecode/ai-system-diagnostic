import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Button {
    id: control
    property var tokens
    property string glyph: "\uE80F"
    property bool active: false
    signal chosen()
    implicitHeight: 54
    leftPadding: 18
    rightPadding: 14
    Accessible.name: text
    onClicked: chosen()
    background: Rectangle {
        color: control.active ? control.tokens.accentSoft : control.hovered ? control.tokens.surfaceHover : "transparent"
        radius: control.tokens.radiusSmall
        border.color: control.visualFocus ? control.tokens.accent : "transparent"
        border.width: 1
        Rectangle { visible: control.active; width: 4; height: parent.height - 12; radius: 2; color: control.tokens.accent; anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter }
        Behavior on color { ColorAnimation { duration: control.tokens.animationFast } }
    }
    contentItem: RowLayout {
        spacing: 14
        AppIcon { tokens: control.tokens; glyph: control.glyph; color: control.active ? control.tokens.info : control.tokens.textSecondary; font.pixelSize: 21; Layout.preferredWidth: 24 }
        Text { text: control.text; color: control.active ? control.tokens.textPrimary : control.tokens.textSecondary; font.family: control.tokens.fontFamily; font.pixelSize: control.tokens.bodySize; font.weight: control.active ? Font.DemiBold : Font.Normal; Layout.fillWidth: true }
    }
}
