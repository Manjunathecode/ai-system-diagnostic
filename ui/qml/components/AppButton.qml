import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

Button {
    id: control
    property var tokens
    property string glyph: ""
    property bool primary: true
    property bool danger: false
    implicitHeight: 48
    implicitWidth: contentRow.implicitWidth + 40
    leftPadding: 18
    rightPadding: 18
    Accessible.name: text

    background: Rectangle {
        radius: control.tokens.radiusSmall
        color: control.danger ? (control.hovered ? "#6A2633" : control.tokens.dangerSoft) :
               control.primary ? (control.hovered ? control.tokens.accentHover : control.tokens.accent) :
               (control.hovered ? control.tokens.surfaceHover : "transparent")
        border.width: control.visualFocus || !control.primary ? 1 : 0
        border.color: control.visualFocus ? control.tokens.textPrimary : control.danger ? control.tokens.danger : control.tokens.accent
        opacity: control.enabled ? 1 : 0.45
        Behavior on color { ColorAnimation { duration: control.tokens.animationFast } }
    }
    contentItem: Item {
        implicitWidth: contentRow.implicitWidth
        implicitHeight: contentRow.implicitHeight
        RowLayout {
            id: contentRow
            anchors.centerIn: parent
            spacing: 10
            AppIcon { visible: control.glyph !== ""; tokens: control.tokens; glyph: control.glyph; color: control.tokens.textPrimary; font.pixelSize: 17; Layout.preferredWidth: visible ? 20 : 0 }
            Text { text: control.text; color: control.tokens.textPrimary; font.family: control.tokens.fontFamily; font.pixelSize: control.tokens.bodySize; font.weight: Font.DemiBold; horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter }
        }
    }
}
