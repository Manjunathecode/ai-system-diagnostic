import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "components"

ApplicationWindow {
    id: window
    visible: true
    width: 1300
    height: 820
    minimumWidth: 1080
    minimumHeight: 700
    title: controller.branding.app_name
    color: theme.canvas
    font.family: theme.fontFamily

    DesignTokens { id: theme }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.preferredWidth: 250
            Layout.fillHeight: true
            color: theme.sidebar
            border.color: theme.border
            border.width: 1
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 5
                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 70
                    spacing: 12
                    Rectangle { width: 38; height: 38; radius: 9; color: theme.accent
                        Image { anchors.fill: parent; anchors.margins: 2; source: controller.branding.logo_url; fillMode: Image.PreserveAspectFit; smooth: true; visible: status === Image.Ready }
                        AppIcon { anchors.centerIn: parent; tokens: theme; glyph: "\uE83D"; color: "white"; font.pixelSize: 23; visible: controller.branding.logo_url === "" }
                    }
                    Text { text: controller.branding.app_name; color: theme.textPrimary; font.family: theme.displayFamily; font.pixelSize: 16; font.weight: Font.Bold; Layout.fillWidth: true; elide: Text.ElideRight }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }
                Repeater {
                    model: [
                        {label:"Dashboard", glyph:"\uE80F"}, {label:"AI Troubleshoot", glyph:"\uE8F2"},
                        {label:"System Scan", glyph:"\uE721"}, {label:"Issues", glyph:"\uE7BA"},
                        {label:"Repair Center", glyph:"\uE90F"}, {label:"System Health", glyph:"\uE95E"},
                        {label:"Reports", glyph:"\uE8A5"}, {label:"Demo Lab", glyph:"\uEC26"},
                        {label:"Settings", glyph:"\uE713"}, {label:"About", glyph:"\uE946"}
                    ]
                    delegate: NavItem { required property var modelData; required property int index; tokens: theme; text: modelData.label; glyph: modelData.glyph; active: controller.currentPage === index; Layout.fillWidth: true; onChosen: controller.navigate(index) }
                }
                Item { Layout.fillHeight: true }
                Rectangle { Layout.fillWidth: true; height: 1; color: theme.border }
                RowLayout { Layout.fillWidth: true; Layout.topMargin: 8
                    AppIcon { tokens: theme; glyph: controller.portableReady ? "\uE73E" : "\uEA39"; color: controller.portableReady ? theme.success : theme.danger; Layout.preferredWidth: 20 }
                    ColumnLayout { Layout.fillWidth: true; spacing: 1
                        Text { text: controller.portableReady ? "Portable storage ready" : "Storage unavailable"; color: theme.textPrimary; font.family: theme.fontFamily; font.pixelSize: 12; font.weight: Font.DemiBold }
                        Text { text: controller.branding.app_tagline; color: theme.textMuted; font.family: theme.fontFamily; font.pixelSize: 11; elide: Text.ElideRight; Layout.fillWidth: true }
                    }
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 58
                color: theme.canvasAlt
                border.color: theme.border
                RowLayout { anchors.fill: parent; anchors.leftMargin: 28; anchors.rightMargin: 28; spacing: 10
                    Text { text: pageTitle(controller.currentPage); color: theme.textSecondary; font.family: theme.fontFamily; font.pixelSize: theme.smallSize; font.weight: Font.DemiBold; Layout.fillWidth: true }
                    StatusPill { tokens: theme; status: controller.privacyMode === "offline_only" ? "ready" : "not_run"; label: controller.privacyMode.replace("_", " ") }
                    StatusPill { tokens: theme; status: controller.isAdministrator ? "ready" : "warning"; label: controller.isAdministrator ? "Administrator" : "Standard user" }
                }
            }

            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true
                StackLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 30; anchors.rightMargin: 30; anchors.topMargin: 16; anchors.bottomMargin: 10
                    currentIndex: controller.currentPage
                    DashboardPage { tokens: theme }
                    TroubleshootPage { tokens: theme }
                    SystemScanPage { tokens: theme }
                    IssuesPage { tokens: theme }
                    RepairCenterPage { tokens: theme }
                    HealthPage { tokens: theme }
                    ReportsPage { tokens: theme }
                    DemoLabPage { tokens: theme }
                    SettingsPage { tokens: theme }
                    AboutPage { tokens: theme }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 40
                color: theme.canvasAlt
                border.color: theme.border
                RowLayout { anchors.fill: parent; anchors.leftMargin: 20; anchors.rightMargin: 20; spacing: 10
                    BusyIndicator { running: controller.busy; visible: running; Layout.preferredWidth: 22; Layout.preferredHeight: 22
                        contentItem: Item { implicitWidth: 22; implicitHeight: 22
                            Rectangle { width: 6; height: 6; radius: 3; color: theme.accent; anchors.top: parent.top; anchors.horizontalCenter: parent.horizontalCenter; transformOrigin: Item.Center
                                RotationAnimator on rotation { running: controller.busy && !controller.reduceMotion; from: 0; to: 360; duration: 900; loops: Animation.Infinite }
                            }
                        }
                    }
                    Text { text: controller.statusMessage; color: theme.textSecondary; font.family: theme.fontFamily; font.pixelSize: 12; Layout.fillWidth: true; elide: Text.ElideRight }
                    Text { text: controller.busy ? controller.progress + "%" : "Safety controls active"; color: controller.busy ? theme.info : theme.success; font.family: theme.fontFamily; font.pixelSize: 12; font.weight: Font.DemiBold }
                }
            }
        }
    }

    Dialog {
        id: confirmationDialog
        objectName: "repairConfirmation"
        modal: true
        anchors.centerIn: Overlay.overlay
        width: 520
        title: "Confirm approved repair"
        standardButtons: Dialog.Yes | Dialog.No
        onAccepted: controller.confirmPendingRepair(true)
        onRejected: controller.confirmPendingRepair(false)
        background: Rectangle { color: theme.surface; border.color: theme.borderStrong; radius: theme.radiusMedium }
        contentItem: ColumnLayout {
            spacing: 12
            Text { text: "Approved workflow: " + (window.pendingProblem.workflowLabel || ""); color: theme.textPrimary; font.family: theme.displayFamily; font.pixelSize: 18; font.weight: Font.Bold; wrapMode: Text.Wrap; Layout.fillWidth: true }
            Text { text: "Risk: " + (window.pendingProblem.riskLabel || "") + "\nAdministrator required: " + ((window.pendingProblem.requiresAdministrator || false) ? "Yes" : "No") + "\n\nThe repair will run only the registered implementation and will be verified afterward."; color: theme.textSecondary; font.family: theme.fontFamily; font.pixelSize: theme.bodySize; wrapMode: Text.Wrap; Layout.fillWidth: true }
        }
    }

    Dialog {
        id: elevationDialog
        objectName: "elevationConfirmation"
        modal: true
        anchors.centerIn: Overlay.overlay
        width: 500
        title: "Administrator permission required"
        standardButtons: Dialog.Yes | Dialog.No
        onAccepted: controller.relaunchElevated()
        onRejected: controller.confirmPendingRepair(false)
        background: Rectangle { color: theme.surface; border.color: theme.warning; radius: theme.radiusMedium }
        contentItem: Text { text: "This approved workflow requires administrator privileges. Restart the application as administrator? No repair will run in this standard-user window."; color: theme.textPrimary; font.family: theme.fontFamily; font.pixelSize: theme.bodySize; wrapMode: Text.Wrap }
    }

    Dialog {
        id: noticeDialog
        objectName: "noticeDialog"
        modal: true
        anchors.centerIn: Overlay.overlay
        width: 500
        title: window.noticeTitle
        standardButtons: Dialog.Ok
        background: Rectangle { color: theme.surface; border.color: theme.borderStrong; radius: theme.radiusMedium }
        contentItem: Text { text: window.noticeMessage; color: theme.textPrimary; font.family: theme.fontFamily; font.pixelSize: theme.bodySize; wrapMode: Text.Wrap }
    }

    property var pendingProblem: ({})
    property string noticeTitle: ""
    property string noticeMessage: ""
    Connections {
        target: controller
        function onConfirmationRequested(problem) { window.pendingProblem = problem; confirmationDialog.open() }
        function onElevationRequested(problem) { window.pendingProblem = problem; elevationDialog.open() }
        function onNotification(title, message) { window.noticeTitle = title; window.noticeMessage = message; noticeDialog.open() }
    }

    Shortcut { sequence: "Ctrl+1"; onActivated: controller.navigate(0) }
    Shortcut { sequence: "Ctrl+2"; onActivated: controller.navigate(1) }
    Shortcut { sequence: "Ctrl+3"; onActivated: controller.navigate(2) }
    Shortcut { sequence: "Ctrl+R"; onActivated: if (!controller.busy) controller.startFullScan() }

    function pageTitle(index) { return ["Dashboard", "AI Troubleshoot", "System Scan", "Issues", "Repair Center", "System Health", "Reports", "Demo Lab", "Settings", "About"][index] }
}
