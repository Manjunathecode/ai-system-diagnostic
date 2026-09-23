import QtQuick 2.15
import QtQuick.Layouts 1.15

RowLayout {
    property var tokens
    property string glyph: "\uE950"
    property string label: "Metric"
    property string value: "Awaiting scan"
    spacing: 12
    AppIcon { tokens: parent.tokens; glyph: parent.glyph; color: parent.tokens.info; Layout.preferredWidth: 22 }
    Text { text: parent.label; color: parent.tokens.textPrimary; font.family: parent.tokens.fontFamily; font.pixelSize: parent.tokens.bodySize; font.weight: Font.DemiBold; Layout.fillWidth: true }
    Text { text: parent.value; color: parent.tokens.textSecondary; font.family: parent.tokens.fontFamily; font.pixelSize: parent.tokens.smallSize }
}
