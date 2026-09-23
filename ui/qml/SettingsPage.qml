import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "components"

ScrollView {
    id: page; property var tokens; clip: true; contentWidth: availableWidth
    ColumnLayout { width: page.availableWidth; spacing: tokens.space20
        PageHeading { tokens: page.tokens; eyebrow: "Portable preferences"; title: "Settings"; subtitle: "Privacy and interface preferences are stored locally beside the application. Credentials remain environment-only."; Layout.fillWidth: true }
        Surface { tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: settingsContent.implicitHeight + 42
            ColumnLayout { id: settingsContent; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 21; spacing: 18
                Text { text: "Privacy mode"; color: tokens.textPrimary; font.family: tokens.displayFamily; font.pixelSize: 19; font.weight: Font.Bold }
                ComboBox { id: privacy; Layout.fillWidth: true; model: ["offline_only", "hybrid_ai", "ai_disabled"]; currentIndex: Math.max(0, model.indexOf(controller.privacyMode)); Accessible.name: "Privacy mode"
                    delegate: ItemDelegate { width: privacy.width; text: modelData.replace("_", " "); font.family: tokens.fontFamily }
                    contentItem: Text { leftPadding: 13; text: privacy.displayText.replace("_", " "); color: tokens.textPrimary; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize; verticalAlignment: Text.AlignVCenter }
                    background: Rectangle { color: tokens.canvasAlt; border.color: privacy.activeFocus ? tokens.accent : tokens.border; radius: tokens.radiusSmall }
                }
                Text { text: privacy.currentText === "offline_only" ? "Guided checks use local troubleshooting rules." : privacy.currentText === "hybrid_ai" ? "This build has no connected online AI provider. It continues using local troubleshooting rules." : "AI reasoning is disabled; local diagnostics and rules remain available."; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true }
                Rectangle { Layout.fillWidth: true; height: 1; color: tokens.border }
                Switch { id: autoFix; text: "Automatically run low-risk approved workflows"; checked: controller.autoFixLowRisk; font.family: tokens.fontFamily; Accessible.name: text
                    contentItem: Text { text: autoFix.text; color: tokens.textPrimary; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize; leftPadding: autoFix.indicator.width + autoFix.spacing }
                }
                Text { text: "Higher-risk workflows always require confirmation. Elevation requirements are never bypassed."; color: tokens.textMuted; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true }
                Switch { id: motion; text: "Reduce interface motion"; checked: controller.reduceMotion; font.family: tokens.fontFamily; Accessible.name: text
                    contentItem: Text { text: motion.text; color: tokens.textPrimary; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize; leftPadding: motion.indicator.width + motion.spacing }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: tokens.border }
                MetricRow { tokens: page.tokens; glyph: "\uE838"; label: "Report location"; value: controller.reportsDirectory; Layout.fillWidth: true }
                MetricRow { tokens: page.tokens; glyph: "\uE9D9"; label: "Logging"; value: "Structured local audit logs enabled"; Layout.fillWidth: true }
                RowLayout { Layout.fillWidth: true; Item { Layout.fillWidth: true }
                    AppButton { tokens: page.tokens; text: "Open report folder"; primary: false; onClicked: controller.openReportsFolder() }
                    AppButton { tokens: page.tokens; text: "Save settings"; glyph: "\uE74E"; onClicked: controller.savePreferences(privacy.currentText, autoFix.checked, motion.checked) }
                }
            }
        }
        Text { text: "API keys, passwords, tokens, and secrets are not displayed or written to reports, SQLite, portable preferences, or UI history."; color: tokens.textMuted; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true }
    }
}
