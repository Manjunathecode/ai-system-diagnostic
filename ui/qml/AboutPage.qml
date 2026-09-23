import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "components"

ScrollView {
    id: page; property var tokens; clip: true; contentWidth: availableWidth
    ColumnLayout { width: page.availableWidth; spacing: tokens.space20
        Surface { tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: 220
            RowLayout { anchors.fill: parent; anchors.margins: 28; spacing: 24
                Rectangle { width: 88; height: 88; radius: 22; color: tokens.accent
                    Image { anchors.fill: parent; anchors.margins: 4; source: controller.branding.logo_url; fillMode: Image.PreserveAspectFit; smooth: true; visible: status === Image.Ready }
                    AppIcon { anchors.centerIn: parent; tokens: page.tokens; glyph: "\uE83D"; color: "white"; font.pixelSize: 46; visible: controller.branding.logo_url === "" }
                }
                ColumnLayout { Layout.fillWidth: true; spacing: 7
                    Text { text: controller.branding.app_name; color: tokens.textPrimary; font.family: tokens.displayFamily; font.pixelSize: 32; font.weight: Font.Bold }
                    Text { text: "Version " + controller.branding.app_version; color: tokens.info; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize }
                    Text { text: "Portable Windows diagnostics with controlled repair and verification workflows"; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Text { text: controller.branding.app_tagline; color: tokens.textMuted; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize }
                }
            }
        }
        GridLayout { Layout.fillWidth: true; columns: width > 900 ? 2 : 1; columnSpacing: 16; rowSpacing: 16
            Repeater { model: [
                {title:"Purpose", text:"Help Windows users collect evidence, understand supported problems, and apply only reviewed recovery workflows."},
                {title:"Safety philosophy", text:"AI and user text cannot execute commands. Confirmation, administrator gates, verification, bounded fallback, and escalation remain mandatory."},
                {title:"Privacy", text:"Offline mode keeps reasoning local. Hybrid mode sends only sanitized, relevant evidence through a configured provider interface."},
                {title:"Capabilities", text:"Windows diagnostics, deterministic detection, conversational routing, controlled repairs, real verification, local audit history, and PDF/CSV/JSON reports."},
                {title:"Limitations", text:"This product does not replace enterprise monitoring, professional hardware repair, malware response, driver installation, or unrestricted system administration."},
                {title:"License", text:"Portfolio and educational project. See the included LICENSE file for distribution terms."}
            ]
                delegate: Surface { required property var modelData; tokens: page.tokens; Layout.fillWidth: true; Layout.preferredHeight: 145
                    ColumnLayout { anchors.fill: parent; anchors.margins: 18; spacing: 7
                        Text { text: modelData.title; color: tokens.textPrimary; font.family: tokens.displayFamily; font.pixelSize: 18; font.weight: Font.Bold }
                        Text { text: modelData.text; color: tokens.textSecondary; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    }
                }
            }
        }
    }
}
