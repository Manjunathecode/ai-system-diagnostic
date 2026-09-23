import QtQuick 2.15
import QtQuick.Layouts 1.15

Rectangle {
    property var tokens
    property string status: "not_run"
    property string label: "Not run"
    property string glyph: status === "passed" || status === "healthy" || status === "resolved" || status === "ready" ? "\uE73E" :
                           status === "warning" || status === "partially_resolved" ? "\uE7BA" :
                           status === "failed" || status === "escalated" ? "\uEA39" : "\uE946"
    implicitWidth: pillRow.implicitWidth + 22
    implicitHeight: 32
    radius: height / 2
    color: tokens.statusSoft(status)
    border.color: tokens.statusColor(status)
    border.width: 1

    RowLayout {
        id: pillRow
        anchors.centerIn: parent
        spacing: 7
        AppIcon { tokens: parent.parent.tokens; glyph: parent.parent.glyph; color: parent.parent.tokens.statusColor(parent.parent.status); font.pixelSize: 14; Layout.preferredWidth: 16 }
        Text { text: parent.parent.label; color: parent.parent.tokens.textPrimary; font.family: parent.parent.tokens.fontFamily; font.pixelSize: parent.parent.tokens.smallSize; font.weight: Font.DemiBold }
    }
}
