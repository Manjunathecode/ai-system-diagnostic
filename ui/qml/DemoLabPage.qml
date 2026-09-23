import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "components"

ScrollView {
    id: page; property var tokens; clip: true; contentWidth: availableWidth
    ColumnLayout { width: page.availableWidth; spacing: tokens.space20
        Rectangle { Layout.fillWidth: true; height: 62; radius: tokens.radiusMedium; color: tokens.warningSoft; border.color: tokens.warning
            RowLayout { anchors.fill: parent; anchors.margins: 16
                AppIcon { tokens: page.tokens; glyph: "\uE7BA"; color: tokens.warning; font.pixelSize: 23; Layout.preferredWidth: 28 }
                Text { text: "DEMO MODE  ·  SIMULATED DATA  ·  NO REAL REPAIR IS BEING PERFORMED"; color: tokens.textPrimary; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize; font.weight: Font.Bold; Layout.fillWidth: true }
            }
        }
        PageHeading { tokens: page.tokens; eyebrow: "Safe portfolio demonstration"; title: "Demo Lab"; subtitle: "Explore complete diagnostic, approved-workflow, verification, and escalation journeys without touching this computer."; Layout.fillWidth: true }
        Surface { visible: controller.demoResult.scenario !== undefined; tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: demoContent.implicitHeight + 34; border.color: tokens.warning
            ColumnLayout { id: demoContent; anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 17; spacing: 8
                Text { text: "Simulated result: " + (controller.demoResult.scenario || ""); color: tokens.textPrimary; font.family: tokens.displayFamily; font.pixelSize: 19; font.weight: Font.Bold }
                Text { text: (controller.demoResult.findings || []).length + " simulated finding(s), " + (controller.demoResult.attempts || []).length + " dry-run attempt(s)."; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize }
                StatusPill { tokens: page.tokens; status: controller.demoResult.escalated ? "escalated" : "passed"; label: controller.demoResult.escalated ? "Simulated escalation" : "Simulation completed" }
                AppButton { tokens: page.tokens; text: "Export simulated PDF"; primary: false; enabled: !controller.busy; onClicked: controller.exportReport("demo", "pdf") }
            }
        }
        GridLayout { Layout.fillWidth: true; columns: width > 900 ? 3 : 2; columnSpacing: 14; rowSpacing: 14
            Repeater { model: [
                {name:"DNS resolution failure", title:"DNS Resolution Failure", detail:"External IP works while name resolution fails.", glyph:"\uE968"},
                {name:"Print Spooler stopped", title:"Print Spooler Stopped", detail:"A simulated spooler service issue.", glyph:"\uE749"},
                {name:"Low disk space", title:"Low Disk Space", detail:"A capacity warning with a controlled cleanup recommendation.", glyph:"\uEDA2"},
                {name:"High CPU usage", title:"High CPU Usage", detail:"A performance finding without an executable repair.", glyph:"\uE950"},
                {name:"Unresolved escalation", title:"Unresolved Issue / Escalation", detail:"Approved fallbacks are exhausted and human action is recommended.", glyph:"\uEA39"}
            ]
                delegate: Surface { required property var modelData; tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: 190
                    ColumnLayout { anchors.fill: parent; anchors.margins: 17; spacing: 9
                        RowLayout { Layout.fillWidth: true
                            Rectangle { width: 42; height: 42; radius: 21; color: tokens.accentSoft; AppIcon { anchors.centerIn: parent; tokens: page.tokens; glyph: modelData.glyph; color: tokens.info; font.pixelSize: 21 } }
                            Text { text: modelData.title; color: tokens.textPrimary; font.family: tokens.displayFamily; font.pixelSize: 18; font.weight: Font.Bold; Layout.fillWidth: true; wrapMode: Text.Wrap }
                        }
                        Text { text: modelData.detail; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true; Layout.fillHeight: true }
                        AppButton { tokens: page.tokens; text: "Run simulation"; primary: false; enabled: !controller.busy; Layout.fillWidth: true; onClicked: controller.runDemo(modelData.name) }
                    }
                }
            }
        }
    }
}
