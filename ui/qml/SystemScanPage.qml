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
        RowLayout {
            Layout.fillWidth: true
            PageHeading { tokens: page.tokens; eyebrow: "Read-only diagnostics"; title: "System Scan"; subtitle: "Collect real Windows evidence without changing this computer."; Layout.fillWidth: true }
            AppButton { tokens: page.tokens; text: controller.busy ? "Scan running…" : "Run system scan"; glyph: "\uE721"; enabled: !controller.busy; onClicked: controller.startFullScan() }
        }
        Surface {
            tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: 108
            ColumnLayout { anchors.fill: parent; anchors.margins: 20; spacing: 10
                RowLayout { Layout.fillWidth: true
                    Text { text: controller.progressLabel; color: tokens.textPrimary; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize; font.weight: Font.DemiBold; Layout.fillWidth: true }
                    Text { text: controller.progress + "%"; color: tokens.info; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize }
                }
                ProgressBar { Layout.fillWidth: true; value: controller.progress / 100
                    background: Rectangle { implicitHeight: 8; radius: 4; color: tokens.canvasAlt }
                    contentItem: Item { Rectangle { width: parent.width * controller.progress / 100; height: 8; radius: 4; color: tokens.accent; Behavior on width { NumberAnimation { duration: controller.reduceMotion ? 0 : tokens.animationNormal } } } }
                }
                Text { text: controller.busy ? "The interface remains responsive while diagnostics run." : "Progress reflects completed diagnostic collectors."; color: tokens.textMuted; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize }
            }
        }
        GridLayout {
            Layout.fillWidth: true; columns: width > 880 ? 3 : 2; columnSpacing: 14; rowSpacing: 14
            Repeater {
                model: controller.scanSections
                delegate: Surface {
                    required property var modelData
                    tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: 126
                    ColumnLayout { anchors.fill: parent; anchors.margins: 16; spacing: 9
                        RowLayout { Layout.fillWidth: true
                            Text { text: modelData.name; color: tokens.textPrimary; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize; font.weight: Font.DemiBold; Layout.fillWidth: true }
                            StatusPill { tokens: page.tokens; status: modelData.status; label: modelData.statusLabel }
                        }
                        Text { text: modelData.summary; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true; maximumLineCount: 2; elide: Text.ElideRight }
                    }
                }
            }
        }
        RowLayout {
            visible: controller.diagnostics.length > 0
            Layout.fillWidth: true
            Repeater { model: [ {label:"Passed checks", value: countStatus("passed")}, {label:"Warnings", value: countStatus("warning")}, {label:"Problems", value: countStatus("failed")}, {label:"Incomplete / error", value: countStatus("not_run") + countStatus("unavailable") + countStatus("permission_required") + countStatus("error")} ]
                delegate: Surface { required property var modelData; tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: 86
                    ColumnLayout { anchors.centerIn: parent
                        Text { text: modelData.value; color: tokens.textPrimary; font.family: tokens.displayFamily; font.pixelSize: 25; font.weight: Font.Bold; Layout.alignment: Qt.AlignHCenter }
                        Text { text: modelData.label; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; Layout.alignment: Qt.AlignHCenter }
                    }
                }
            }
        }
    }
    function countStatus(status) { var count = 0; for (var i = 0; i < controller.diagnostics.length; ++i) if (controller.diagnostics[i].status === status) count++; return count }
}
