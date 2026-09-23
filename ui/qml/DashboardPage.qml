import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "components"

ScrollView {
    id: page
    property var tokens
    clip: true
    contentWidth: availableWidth

    ColumnLayout {
        width: page.availableWidth
        spacing: tokens.space24

        GridLayout {
            Layout.fillWidth: true
            columns: width >= 940 ? 2 : 1
            columnSpacing: tokens.space32
            rowSpacing: tokens.space24

            ColumnLayout {
                Layout.fillWidth: true
                Layout.preferredWidth: 610
                spacing: tokens.space20
                PageHeading { tokens: page.tokens; eyebrow: "Welcome"; title: "How can I help this PC today?"; subtitle: "Describe the problem in your own words and I’ll guide you to the right next steps."; Layout.fillWidth: true }

                TextArea {
                    id: symptomInput
                    Layout.fillWidth: true
                    Layout.preferredHeight: 92
                    placeholderText: "Describe what is happening…"
                    wrapMode: TextArea.Wrap
                    color: tokens.textPrimary
                    placeholderTextColor: tokens.textMuted
                    font.family: tokens.fontFamily
                    font.pixelSize: 17
                    padding: 22
                    Accessible.name: "Describe the IT problem"
                    background: Rectangle { color: tokens.surface; radius: tokens.radiusMedium; border.color: symptomInput.activeFocus ? tokens.accent : tokens.borderStrong; border.width: symptomInput.activeFocus ? 2 : 1 }
                    Keys.onPressed: function(event) { if (guidedButton.enabled && (event.modifiers & Qt.ControlModifier) && event.key === Qt.Key_Return) { guidedButton.clicked(); event.accepted = true } }
                }

                AppButton {
                    id: guidedButton
                    tokens: page.tokens
                    text: "Start guided check"
                    glyph: "\uE72A"
                    Layout.fillWidth: true
                    enabled: !controller.busy && symptomInput.text.trim().length > 0
                    onClicked: controller.startTroubleshooting(symptomInput.text)
                }
                Text { text: "Your description is context only. It can never run commands."; color: tokens.textMuted; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; Layout.alignment: Qt.AlignHCenter }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: tokens.space16
                    Surface {
                        tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: 98
                        MouseArea { objectName: "dashboardScanAction"; anchors.fill: parent; enabled: !controller.busy; cursorShape: Qt.PointingHandCursor; onClicked: { controller.navigate(2); controller.startFullScan() } }
                        RowLayout { anchors.fill: parent; anchors.margins: 18; spacing: 14
                            Rectangle { width: 48; height: 48; radius: 24; color: tokens.accentSoft
                                AppIcon { anchors.centerIn: parent; tokens: page.tokens; glyph: "\uE721"; color: tokens.textPrimary; font.pixelSize: 24 }
                            }
                            ColumnLayout { Layout.fillWidth: true; spacing: 4
                                Text { text: "Run a full system scan"; color: tokens.textPrimary; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize; font.weight: Font.DemiBold }
                                Text { text: "Check this PC with read-only diagnostics."; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true }
                            }
                            AppIcon { tokens: page.tokens; glyph: "\uE76C"; color: tokens.textSecondary }
                        }
                    }
                    Surface {
                        tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: 98
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: controller.navigate(3) }
                        RowLayout { anchors.fill: parent; anchors.margins: 18; spacing: 14
                            Rectangle { width: 48; height: 48; radius: 24; color: tokens.accentSoft
                                AppIcon { anchors.centerIn: parent; tokens: page.tokens; glyph: "\uE8A5"; color: tokens.textPrimary; font.pixelSize: 24 }
                            }
                            ColumnLayout { Layout.fillWidth: true; spacing: 4
                                Text { text: "Review known issues"; color: tokens.textPrimary; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize; font.weight: Font.DemiBold }
                                Text { text: controller.problems.length ? controller.problems.length + " detected issue(s)." : "No current detected issues."; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true }
                            }
                            AppIcon { tokens: page.tokens; glyph: "\uE76C"; color: tokens.textSecondary }
                        }
                    }
                }
            }

            Surface {
                tokens: page.tokens
                Layout.fillWidth: true
                Layout.preferredWidth: 330
                Layout.preferredHeight: 430
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: tokens.space24
                    spacing: tokens.space16
                    RowLayout { spacing: 12
                        AppIcon { tokens: page.tokens; glyph: "\uE83D"; color: tokens.accent; font.pixelSize: 29; Layout.preferredWidth: 34 }
                        ColumnLayout { spacing: 2
                            Text { text: "Device readiness"; color: tokens.textPrimary; font.family: tokens.displayFamily; font.pixelSize: tokens.headingSize; font.weight: Font.Bold }
                            Text { text: "Key states for a safe session."; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize }
                        }
                    }
                    Rectangle { Layout.fillWidth: true; height: 1; color: tokens.border }
                    MetricRow { tokens: page.tokens; glyph: "\uE95E"; label: "System health"; value: controller.dashboard.health; Layout.fillWidth: true }
                    Rectangle { Layout.fillWidth: true; height: 1; color: tokens.border }
                    MetricRow { tokens: page.tokens; glyph: "\uE83D"; label: "Administrator"; value: controller.isAdministrator ? "Enabled" : "Not enabled"; Layout.fillWidth: true }
                    Rectangle { Layout.fillWidth: true; height: 1; color: tokens.border }
                    MetricRow { tokens: page.tokens; glyph: "\uE72E"; label: "Privacy"; value: controller.privacyMode.replace("_", " "); Layout.fillWidth: true }
                    Rectangle { Layout.fillWidth: true; height: 1; color: tokens.border }
                    MetricRow { tokens: page.tokens; glyph: "\uEC26"; label: "Portable storage"; value: controller.portableReady ? "Ready" : "Unavailable"; Layout.fillWidth: true }
                    Item { Layout.fillHeight: true }
                    Rectangle { Layout.fillWidth: true; height: safetyNote.implicitHeight + 28; radius: tokens.radiusSmall; color: tokens.canvasAlt; border.color: tokens.border
                        RowLayout { id: safetyNote; anchors.left: parent.left; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; anchors.margins: 14; spacing: 10
                            AppIcon { tokens: page.tokens; glyph: "\uE73E"; color: tokens.info; Layout.preferredWidth: 20 }
                            Text { Layout.fillWidth: true; text: "Designed to be safe, private, and under your control. No changes are made without approval."; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; wrapMode: Text.Wrap }
                        }
                    }
                }
            }
        }

        Surface {
            tokens: page.tokens
            Layout.fillWidth: true
            Layout.preferredHeight: 230
            ColumnLayout {
                anchors.fill: parent; anchors.margins: tokens.space24; spacing: tokens.space16
                RowLayout { Layout.fillWidth: true
                    ColumnLayout { spacing: 3
                        Text { text: "Your guided safety journey"; color: tokens.textPrimary; font.family: tokens.displayFamily; font.pixelSize: tokens.headingSize; font.weight: Font.Bold }
                        Text { text: "A controlled path from diagnosis to verified outcome."; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize }
                    }
                    Item { Layout.fillWidth: true }
                    Text { text: "Safe steps. Real support. Better outcomes."; color: tokens.textMuted; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize }
                }
                RowLayout {
                    Layout.fillWidth: true; Layout.fillHeight: true; spacing: 8
                    Repeater {
                        model: [ {label:"Diagnose", detail:"Understand what’s happening", glyph:"\uE721"}, {label:"Approved workflow", detail:"Use reviewed actions only", glyph:"\uE8A5"}, {label:"Confirm", detail:"You approve before changes", glyph:"\uE73A"}, {label:"Verify", detail:"Check the real outcome", glyph:"\uE73E"} ]
                        delegate: RowLayout {
                            required property var modelData
                            required property int index
                            Layout.fillWidth: true
                            ColumnLayout { Layout.fillWidth: true; spacing: 7
                                Rectangle { Layout.alignment: Qt.AlignHCenter; width: 54; height: 54; radius: 27; color: tokens.accentSoft; border.color: tokens.accent
                                    AppIcon { anchors.centerIn: parent; tokens: page.tokens; glyph: modelData.glyph; color: tokens.textPrimary; font.pixelSize: 23 }
                                }
                                Text { Layout.alignment: Qt.AlignHCenter; text: modelData.label; color: tokens.textPrimary; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize; font.weight: Font.DemiBold }
                                Text { Layout.alignment: Qt.AlignHCenter; text: modelData.detail; color: tokens.textMuted; font.family: tokens.fontFamily; font.pixelSize: 12; horizontalAlignment: Text.AlignHCenter }
                            }
                            Rectangle { visible: index < 3; Layout.fillWidth: true; Layout.minimumWidth: 24; height: 1; color: tokens.borderStrong }
                        }
                    }
                }
                Rectangle { Layout.fillWidth: true; height: 42; radius: tokens.radiusSmall; color: tokens.canvasAlt; border.color: tokens.border
                    RowLayout { anchors.fill: parent; anchors.margins: 10
                        AppIcon { tokens: page.tokens; glyph: "\uE946"; color: tokens.info; Layout.preferredWidth: 20 }
                        Text { text: "Your description is context only. It can never run commands."; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; Layout.fillWidth: true }
                        Text { text: "Your PC. In your control."; color: tokens.textMuted; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize }
                    }
                }
            }
        }
    }
}
