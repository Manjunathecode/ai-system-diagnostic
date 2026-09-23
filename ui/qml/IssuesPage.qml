import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "components"

ScrollView {
    id: page; property var tokens; clip: true; contentWidth: availableWidth
    ColumnLayout { width: page.availableWidth; spacing: tokens.space20
        RowLayout { Layout.fillWidth: true
            PageHeading { tokens: page.tokens; eyebrow: "Detected evidence"; title: "Issues"; subtitle: "Only problems supported by deterministic rules and the Approved Fix Registry appear here."; Layout.fillWidth: true }
            AppButton { tokens: page.tokens; text: "Run scan"; glyph: "\uE721"; primary: false; enabled: !controller.busy; onClicked: controller.startFullScan() }
        }
        Surface { visible: controller.problems.length === 0; tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: 210
            ColumnLayout { anchors.centerIn: parent; spacing: 10
                AppIcon { tokens: page.tokens; glyph: "\uE946"; color: tokens.textMuted; font.pixelSize: 34; Layout.alignment: Qt.AlignHCenter }
                Text { text: "No detected problems to display"; color: tokens.textPrimary; font.family: tokens.displayFamily; font.pixelSize: tokens.headingSize; font.weight: Font.Bold }
                Text { text: "Run a system scan or start guided troubleshooting."; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize; Layout.alignment: Qt.AlignHCenter }
            }
        }
        Repeater { model: controller.problems
            delegate: Surface { required property var modelData; required property int index; tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: issueContent.implicitHeight + 38
                ColumnLayout { id: issueContent; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 19; spacing: 12
                    RowLayout { Layout.fillWidth: true
                        ColumnLayout { Layout.fillWidth: true; spacing: 3
                            Text { text: modelData.title; color: tokens.textPrimary; font.family: tokens.displayFamily; font.pixelSize: 19; font.weight: Font.Bold; wrapMode: Text.Wrap; Layout.fillWidth: true }
                            Text { text: modelData.category + "  •  " + modelData.confidenceLabel + " deterministic confidence"; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize }
                        }
                        StatusPill { tokens: page.tokens; status: modelData.severity === "high" || modelData.severity === "critical" ? "failed" : "warning"; label: modelData.severityLabel }
                    }
                    Text { visible: !modelData.repairAvailable; text: modelData.repairUnavailableReason || "This finding needs manual review; no automatic repair is available."; color: tokens.warning; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Rectangle { Layout.fillWidth: true; height: 1; color: tokens.border }
                    GridLayout { Layout.fillWidth: true; columns: 2; columnSpacing: 24; rowSpacing: 9
                        Text { text: "Evidence"; color: tokens.textMuted; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; font.weight: Font.DemiBold }
                        Text { text: modelData.evidenceText; color: tokens.textPrimary; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true }
                        Text { text: "Approved workflow"; color: tokens.textMuted; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; font.weight: Font.DemiBold }
                        Text { text: modelData.workflowLabel; color: tokens.info; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; Layout.fillWidth: true }
                        Text { text: "Safety"; color: tokens.textMuted; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; font.weight: Font.DemiBold }
                        Text { text: modelData.riskLabel + " risk • " + (modelData.requiresAdministrator ? "Administrator required" : "Standard user supported") + " • " + (modelData.requiresConfirmation ? "Confirmation required" : "No extra confirmation"); color: tokens.textPrimary; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    }
                    RowLayout { Layout.fillWidth: true
                        Item { Layout.fillWidth: true }
                        AppButton { tokens: page.tokens; text: "View evidence"; primary: false; onClicked: evidence.visible = !evidence.visible }
                        AppButton { tokens: page.tokens; text: "Repair"; glyph: "\uE90F"; enabled: modelData.repairAvailable && !controller.busy; onClicked: controller.requestRepair(index) }
                    }
                    Text { id: evidence; visible: false; text: modelData.evidenceText; color: tokens.textSecondary; font.family: "Consolas"; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                }
            }
        }
    }
}
