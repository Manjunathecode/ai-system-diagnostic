import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "components"

ScrollView {
    id: page; property var tokens; clip: true; contentWidth: availableWidth
    ColumnLayout { width: page.availableWidth; spacing: tokens.space20
        RowLayout { Layout.fillWidth: true
            PageHeading { tokens: page.tokens; eyebrow: "Collected evidence"; title: "System Health"; subtitle: "Expand real findings from the latest locally stored scan."; Layout.fillWidth: true }
            StatusPill { tokens: page.tokens; status: controller.dashboard.health; label: controller.dashboard.health }
        }
        Surface { visible: controller.diagnostics.length === 0; tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: 180
            ColumnLayout { anchors.centerIn: parent; spacing: 8
                Text { text: "System health has not been checked"; color: tokens.textPrimary; font.family: tokens.displayFamily; font.pixelSize: tokens.headingSize; font.weight: Font.Bold }
                Text { text: "Run a scan to collect CPU, memory, storage, network, service, printer, device, and system evidence."; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize }
                AppButton { tokens: page.tokens; text: "Run system scan"; Layout.alignment: Qt.AlignHCenter; enabled: !controller.busy; onClicked: controller.startFullScan() }
            }
        }
        Repeater { model: controller.diagnostics
            delegate: Surface { required property var modelData; tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: details.visible ? 280 : 112
                Behavior on Layout.preferredHeight { NumberAnimation { duration: controller.reduceMotion ? 0 : tokens.animationNormal } }
                ColumnLayout { anchors.fill: parent; anchors.margins: 16; spacing: 8
                    RowLayout { Layout.fillWidth: true
                        AppIcon { tokens: page.tokens; glyph: "\uE9D9"; color: tokens.info; Layout.preferredWidth: 24 }
                        ColumnLayout { Layout.fillWidth: true
                            Text { text: modelData.name; color: tokens.textPrimary; font.family: tokens.displayFamily; font.pixelSize: 18; font.weight: Font.Bold }
                            Text { text: modelData.category + " · " + modelData.summary; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; elide: Text.ElideRight; Layout.fillWidth: true }
                        }
                        StatusPill { tokens: page.tokens; status: modelData.status; label: modelData.statusLabel }
                        AppButton { tokens: page.tokens; text: details.visible ? "Hide evidence" : "View evidence"; primary: false; onClicked: details.visible = !details.visible }
                    }
                    ScrollView { id: details; visible: false; Layout.fillWidth: true; Layout.fillHeight: true
                        TextArea { text: modelData.detailsText; readOnly: true; color: tokens.textSecondary; selectionColor: tokens.accent; selectedTextColor: tokens.textPrimary; font.family: "Consolas"; font.pixelSize: 12; wrapMode: TextArea.WrapAnywhere; background: Rectangle { color: tokens.canvasAlt; radius: 7; border.color: tokens.border } }
                    }
                }
            }
        }
    }
}

