import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "components"

Item {
    id: page
    property var tokens
    ColumnLayout {
        anchors.fill: parent; spacing: tokens.space20
        PageHeading { tokens: page.tokens; eyebrow: "Conversational troubleshooting"; title: "AI Troubleshoot"; subtitle: "Your words are context only. Diagnostics and repairs remain deterministic and approved."; Layout.fillWidth: true }
        RowLayout { Layout.fillWidth: true; spacing: 10
            Repeater { model: ["Understanding", "Follow-up", "Diagnostics", "Analysis", "Problem identified", "Approved workflow"]
                delegate: Rectangle { required property string modelData; required property int index; Layout.fillWidth: true; height: 38; radius: 7; color: index <= stageIndex() ? tokens.accentSoft : tokens.surface; border.color: index <= stageIndex() ? tokens.accent : tokens.border
                    Text { anchors.centerIn: parent; text: modelData; color: tokens.textPrimary; font.family: tokens.fontFamily; font.pixelSize: 12; font.weight: Font.DemiBold }
                }
            }
        }
        Surface {
            tokens: page.tokens; Layout.fillWidth: true; Layout.fillHeight: true
            ColumnLayout { anchors.fill: parent; anchors.margins: 18; spacing: 12
                ListView {
                    id: chatList; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 12; model: controller.chatMessages
                    delegate: Item { required property var modelData; width: chatList.width; height: bubble.implicitHeight
                        Rectangle { id: bubble; width: Math.min(parent.width * 0.78, messageText.implicitWidth + 34); implicitHeight: messageText.implicitHeight + 26; radius: 12;
                            anchors.right: modelData.role === "user" ? parent.right : undefined; anchors.left: modelData.role === "user" ? undefined : parent.left
                            color: modelData.role === "user" ? tokens.accentSoft : tokens.canvasAlt; border.color: modelData.role === "user" ? tokens.accent : tokens.border
                            Text { id: messageText; anchors.fill: parent; anchors.margins: 13; text: modelData.content; color: tokens.textPrimary; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize; wrapMode: Text.Wrap; width: Math.min(chatList.width * .72, 720) }
                        }
                    }
                    footer: Item { width: 1; height: 8 }
                    onCountChanged: positionViewAtEnd()
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: tokens.border }
                Text { visible: controller.session.question !== undefined && controller.session.question !== ""; text: "Follow-up: " + controller.session.question; color: tokens.warning; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; wrapMode: Text.Wrap; Layout.fillWidth: true }
                RowLayout { Layout.fillWidth: true; spacing: 12
                    TextArea { id: input; Layout.fillWidth: true; Layout.preferredHeight: 74; placeholderText: controller.session.sessionId ? "Answer the follow-up question…" : "Describe the issue…"; wrapMode: TextArea.Wrap; color: tokens.textPrimary; placeholderTextColor: tokens.textMuted; font.family: tokens.fontFamily; font.pixelSize: tokens.bodySize; padding: 14; Accessible.name: placeholderText
                        background: Rectangle { color: tokens.canvasAlt; radius: tokens.radiusSmall; border.color: input.activeFocus ? tokens.accent : tokens.border }
                    }
                    AppButton { tokens: page.tokens; text: controller.session.sessionId ? "Continue" : "Start"; glyph: "\uE72A"; enabled: !controller.busy && input.text.trim().length > 0; onClicked: { if (controller.session.sessionId) controller.continueTroubleshooting(input.text); else controller.startTroubleshooting(input.text); input.clear() } }
                    AppButton { tokens: page.tokens; text: "New issue"; primary: false; enabled: !controller.busy && !!controller.session.sessionId; onClicked: { controller.resetTroubleshooting(); input.clear() } }
                }
                RowLayout { Layout.fillWidth: true
                    AppIcon { tokens: page.tokens; glyph: "\uE946"; color: tokens.info; Layout.preferredWidth: 18 }
                    Text { text: "Natural-language text never becomes PowerShell, CMD, Python, or shell input."; color: tokens.textMuted; font.family: tokens.fontFamily; font.pixelSize: tokens.smallSize; Layout.fillWidth: true }
                    AppButton { visible: controller.problems.length > 0; tokens: page.tokens; text: "Review recommended fix"; primary: false; onClicked: controller.navigate(3) }
                }
            }
        }
    }
    function stageIndex() { var s = controller.session.status || ""; if (!controller.session.sessionId) return -1; if (s === "awaiting_follow_up") return 1; if (s === "repair_recommended") return 5; if (s === "inconclusive" || s === "needs_more_information") return 3; return 2 }
}
