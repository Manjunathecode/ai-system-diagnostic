import QtQuick 2.15
import QtQuick.Layouts 1.15

ColumnLayout {
    property var tokens
    property string eyebrow: ""
    property string title: ""
    property string subtitle: ""
    spacing: 5
    Text { visible: parent.eyebrow !== ""; text: parent.eyebrow; color: parent.tokens.accent; font.family: parent.tokens.fontFamily; font.pixelSize: parent.tokens.bodySize; font.weight: Font.DemiBold }
    Text { text: parent.title; color: parent.tokens.textPrimary; font.family: parent.tokens.displayFamily; font.pixelSize: parent.tokens.titleSize; font.weight: Font.Bold; wrapMode: Text.Wrap }
    Text { visible: parent.subtitle !== ""; text: parent.subtitle; color: parent.tokens.textSecondary; font.family: parent.tokens.fontFamily; font.pixelSize: parent.tokens.bodySize; wrapMode: Text.Wrap; Layout.maximumWidth: 760 }
}
