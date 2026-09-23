import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "components"

ScrollView {
    id: page; property var tokens; clip: true; contentWidth: availableWidth
    ColumnLayout { width: page.availableWidth; spacing: tokens.space20
        RowLayout { Layout.fillWidth: true
            PageHeading { tokens: page.tokens; eyebrow: "Local evidence export"; title: "Report Center"; subtitle: "Generate sanitized PDF, CSV, or JSON files from persisted SQLite evidence."; Layout.fillWidth: true }
            ComboBox { id: format; model: ["PDF", "CSV", "JSON"]; Accessible.name: "Report format"; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize
                background: Rectangle { color: tokens.surface; border.color: format.activeFocus ? tokens.accent : tokens.border; radius: tokens.radiusSmall }
                contentItem: Text { leftPadding: 12; text: format.displayText; color: tokens.textPrimary; font: format.font; verticalAlignment: Text.AlignVCenter }
            }
            AppButton { tokens: page.tokens; text: "Open report folder"; primary: false; glyph: "\uE838"; onClicked: controller.openReportsFolder() }
        }
        GridLayout { Layout.fillWidth: true; columns: width > 900 ? 4 : 2; columnSpacing: 12; rowSpacing: 12
            Repeater { model: [ {title:"Current session", kind:"session", detail:"Conversation, diagnostics, recommendation and verified outcome."}, {title:"Diagnostic report", kind:"diagnostic", detail:"Latest collected system-health evidence."}, {title:"Escalation report", kind:"escalation", detail:"Remaining symptoms and recommended human action."}, {title:"Activity summary", kind:"summary", detail:"Counts from locally persisted scans, sessions and repairs."} ]
                delegate: Surface { required property var modelData; tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: 180
                    ColumnLayout { anchors.fill: parent; anchors.margins: 16; spacing: 8
                        Text { text: modelData.title; color: tokens.textPrimary; font.family: tokens.displayFamily; font.pixelSize: 18; font.weight: Font.Bold }
                        Text { text: modelData.detail; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true; Layout.fillHeight: true }
                        AppButton { tokens: page.tokens; text: "Export " + format.currentText; primary: false; enabled: !controller.busy && (modelData.kind === "summary" || (modelData.kind === "session" && !!controller.session.sessionId) || (modelData.kind === "diagnostic" && controller.dashboard.lastScan !== "Not yet run") || (modelData.kind === "escalation" && controller.session.status === "escalated")); Layout.fillWidth: true; onClicked: controller.exportReport(modelData.kind, format.currentText.toLowerCase()) }
                    }
                }
            }
        }
        RowLayout { Layout.fillWidth: true
            Text { text: "Report history"; color: tokens.textPrimary; font.family: tokens.displayFamily; font.pixelSize: tokens.headingSize; font.weight: Font.Bold; Layout.fillWidth: true }
            AppButton { tokens: page.tokens; text: "Refresh"; primary: false; onClicked: controller.refreshReports() }
        }
        Surface { visible: controller.reports.length === 0; tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: 120
            Text { anchors.centerIn: parent; text: "No generated reports yet."; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize }
        }
        Repeater { model: controller.reports
            delegate: Surface { required property var modelData; tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: 72
                RowLayout { anchors.fill: parent; anchors.margins: 14; spacing: 12
                    StatusPill { tokens: page.tokens; status: "ready"; label: modelData.format }
                    ColumnLayout { Layout.fillWidth: true
                        Text { text: modelData.name; color: tokens.textPrimary; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize; font.weight: Font.DemiBold; elide: Text.ElideMiddle; Layout.fillWidth: true }
                        Text { text: modelData.generated_at + " · " + modelData.size_bytes + " bytes"; color: tokens.textMuted; font.family: tokens.fontFamily; font.pixelSize: 11 }
                    }
                    AppButton { tokens: page.tokens; text: "Open"; primary: false; onClicked: controller.openReport(modelData.path) }
                }
            }
        }
        Text { text: "Reports distinguish recommendations from verified outcomes. Missing evidence stays missing; it is never fabricated."; color: tokens.textMuted; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true }
    }
}
