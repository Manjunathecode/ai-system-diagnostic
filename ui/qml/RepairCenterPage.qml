import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "components"

ScrollView {
    id: page; property var tokens; clip: true; contentWidth: availableWidth
    ColumnLayout { width: page.availableWidth; spacing: tokens.space24
        PageHeading { tokens: page.tokens; eyebrow: "Controlled recovery"; title: "Repair Center"; subtitle: "Every repair follows the registry, safety checks, confirmation, execution, and deterministic verification."; Layout.fillWidth: true }
        RowLayout { Layout.fillWidth: true; spacing: 8
            Repeater { model: ["Pre-check", "Approved workflow", "Safety validation", "Confirmation", "Repair", "Verification", "Final result"]
                delegate: Rectangle { required property string modelData; required property int index; Layout.fillWidth: true; height: 42; radius: 7; color: index < repairStage() ? tokens.accentSoft : tokens.surface; border.color: index < repairStage() ? tokens.accent : tokens.border
                    Text { anchors.centerIn: parent; width: parent.width - 10; text: modelData; color: tokens.textPrimary; font.family: tokens.fontFamily; font.pixelSize: 11; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap }
                }
            }
        }
        Surface { visible: controller.repairTimeline.length === 0 && !controller.busy; tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: 190
            ColumnLayout { anchors.centerIn: parent; spacing: 9
                AppIcon { tokens: page.tokens; glyph: "\uE90F"; color: tokens.textMuted; font.pixelSize: 36; Layout.alignment: Qt.AlignHCenter }
                Text { text: "No repair attempt is active"; color: tokens.textPrimary; font.family: tokens.displayFamily; font.pixelSize: tokens.headingSize; font.weight: Font.Bold }
                Text { text: "Choose Repair on a detected issue to begin the controlled workflow."; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize }
                AppButton { tokens: page.tokens; text: "View issues"; primary: false; Layout.alignment: Qt.AlignHCenter; onClicked: controller.navigate(3) }
            }
        }
        Repeater { model: controller.repairTimeline
            delegate: Surface { required property var modelData; required property int index; tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: repairContent.implicitHeight + 38
                ColumnLayout { id: repairContent; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 19; spacing: 12
                    RowLayout { Layout.fillWidth: true
                        ColumnLayout { Layout.fillWidth: true
                            Text { text: "Attempt " + (index + 1) + " · " + modelData.workflowLabel; color: tokens.textPrimary; font.family: tokens.displayFamily; font.pixelSize: 19; font.weight: Font.Bold }
                            Text { text: modelData.durationSeconds + " seconds · " + modelData.completedAt; color: tokens.textMuted; font.family: tokens.fontFamily; font.pixelSize: 12 }
                        }
                        StatusPill { tokens: page.tokens; status: modelData.status; label: modelData.statusLabel }
                    }
                    Text { text: modelData.message; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    GridLayout { Layout.fillWidth: true; columns: width > 780 ? 3 : 1; columnSpacing: 12; rowSpacing: 12
                        Surface { tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: 150
                            ColumnLayout { anchors.fill: parent; anchors.margins: 14
                                Text { text: "Before repair"; color: tokens.textPrimary; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; font.weight: Font.Bold }
                                ScrollView { Layout.fillWidth: true; Layout.fillHeight: true; TextArea { text: modelData.beforeText; readOnly: true; color: tokens.textSecondary; font.family: "Consolas"; font.pixelSize: 11; background: Item {} } }
                            }
                        }
                        Surface { tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: 150
                            ColumnLayout { anchors.fill: parent; anchors.margins: 14
                                Text { text: "After repair"; color: tokens.textPrimary; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; font.weight: Font.Bold }
                                ScrollView { Layout.fillWidth: true; Layout.fillHeight: true; TextArea { text: modelData.afterText; readOnly: true; color: tokens.textSecondary; font.family: "Consolas"; font.pixelSize: 11; background: Item {} } }
                            }
                        }
                        Surface { tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: 150
                            ColumnLayout { anchors.fill: parent; anchors.margins: 14
                                Text { text: "Verification"; color: tokens.textPrimary; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; font.weight: Font.Bold }
                                Text { text: modelData.verificationText; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: 12; wrapMode: Text.Wrap; Layout.fillWidth: true }
                                Item { Layout.fillHeight: true }
                                Text { text: "Evidence confidence: " + modelData.confidence + "%"; color: tokens.info; font.family: tokens.fontFamily; font.pixelSize: 12 }
                            }
                        }
                    }
                }
            }
        }
        Surface { visible: controller.escalation.recommendedHumanAction !== undefined; tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: 130; color: tokens.dangerSoft; border.color: tokens.danger
            ColumnLayout { anchors.fill: parent; anchors.margins: 18
                Text { text: "Escalated"; color: tokens.danger; font.family: tokens.displayFamily; font.pixelSize: 19; font.weight: Font.Bold }
                Text { text: controller.escalation.recommendedHumanAction || ""; color: tokens.textPrimary; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize; wrapMode: Text.Wrap; Layout.fillWidth: true }
                Text { text: (controller.escalation.remainingSymptoms || []).join(" · "); color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true }
            }
        }
    }
    function repairStage() { return controller.repairTimeline.length ? 7 : 0 }
}
