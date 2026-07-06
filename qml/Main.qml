import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ApplicationWindow {
    id: root
    visible: true
    width: 1180
    height: 760
    title: "Loupedeck Config"
    color: theme.bg

    // ---- dark theme tokens ------------------------------------------------
    QtObject {
        id: theme
        readonly property color bg: "#15151b"
        readonly property color panel: "#1e1e27"
        readonly property color panel2: "#262631"
        readonly property color cell: "#2b2b37"
        readonly property color line: "#33333f"
        readonly property color text: "#dcdce4"
        readonly property color muted: "#8a8a9a"
        readonly property color accent: "#3d8bfd"
        readonly property color ok: "#3fbf7f"
        readonly property int radius: 10
    }

    // ============================ TOP BAR =================================
    header: Rectangle {
        height: 58
        color: theme.panel
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: theme.line }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            spacing: 14

            // device pill
            Rectangle {
                Layout.preferredWidth: 190; Layout.preferredHeight: 34
                radius: theme.radius; color: theme.panel2; border.color: theme.line
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 8
                    Rectangle { width: 9; height: 9; radius: 5
                        color: backend.connected ? theme.ok : theme.muted }
                    Text { text: backend.deviceName; color: theme.text; font.pixelSize: 14; font.bold: true
                        Layout.fillWidth: true; elide: Text.ElideRight }
                }
            }

            Item { Layout.fillWidth: true }

            Text { text: "Profile:"; color: theme.muted; font.pixelSize: 13 }
            Rectangle {
                Layout.preferredWidth: 160; Layout.preferredHeight: 34
                radius: theme.radius; color: theme.panel2; border.color: theme.line
                Text { anchors.centerIn: parent; text: backend.activeProfile; color: theme.text; font.pixelSize: 13 }
            }

            // dynamic mode toggle
            RowLayout {
                spacing: 8
                Text { text: "Dynamic"; color: theme.muted; font.pixelSize: 13 }
                Switch {
                    checked: backend.dynamicMode
                    onToggled: backend.setDynamicMode(checked)
                }
            }
        }
    }

    // ============================ BODY (3 columns) =========================
    RowLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 12

        // ---------- LEFT: action library ----------
        Rectangle {
            Layout.preferredWidth: 250; Layout.fillHeight: true
            radius: theme.radius; color: theme.panel; border.color: theme.line
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 12; spacing: 10
                Text { text: "Actions"; color: theme.text; font.pixelSize: 15; font.bold: true }
                Rectangle {
                    Layout.fillWidth: true; height: 32; radius: theme.radius
                    color: theme.panel2; border.color: theme.line
                    Text { anchors.verticalCenter: parent.verticalCenter; anchors.left: parent.left
                        anchors.leftMargin: 10; text: "Search actions…"; color: theme.muted; font.pixelSize: 13 }
                }
                ListView {
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 4
                    model: backend.actionCategories
                    delegate: Rectangle {
                        width: ListView.view.width; height: 40; radius: theme.radius
                        color: theme.panel2
                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 10; spacing: 10
                            Rectangle { width: 20; height: 20; radius: 5; color: theme.accent; opacity: 0.8 }
                            Text { text: modelData; color: theme.text; font.pixelSize: 13; Layout.fillWidth: true }
                            Text { text: "›"; color: theme.muted; font.pixelSize: 16; rightPadding: 10 }
                        }
                    }
                }
            }
        }

        // ---------- CENTER: device view ----------
        Rectangle {
            Layout.fillWidth: true; Layout.fillHeight: true
            radius: theme.radius; color: theme.panel; border.color: theme.line
            DeviceView {
                anchors.centerIn: parent
                theme: theme
            }
        }

        // ---------- RIGHT: profiles / pages ----------
        Rectangle {
            Layout.preferredWidth: 270; Layout.fillHeight: true
            radius: theme.radius; color: theme.panel; border.color: theme.line
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 12; spacing: 10
                Text { text: "Profiles"; color: theme.text; font.pixelSize: 15; font.bold: true }
                ListView {
                    Layout.fillWidth: true; Layout.preferredHeight: 220; clip: true; spacing: 4
                    model: backend.profiles
                    delegate: Rectangle {
                        width: ListView.view.width; height: 38; radius: theme.radius
                        color: modelData === backend.activeProfile ? theme.accent
                               : (hover.hovered ? theme.cell : theme.panel2)
                        opacity: modelData === backend.activeProfile ? 0.9 : 1.0
                        HoverHandler { id: hover }
                        TapHandler { onTapped: backend.loadProfile(modelData) }
                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 10; spacing: 8
                            Text { text: "▦"; color: theme.muted; font.pixelSize: 14 }
                            Text { text: modelData; color: theme.text; font.pixelSize: 13; Layout.fillWidth: true; elide: Text.ElideRight }
                        }
                    }
                }
                Rectangle { Layout.fillWidth: true; height: 1; color: theme.line }
                Text { text: "Pages"; color: theme.text; font.pixelSize: 15; font.bold: true }
                Text { text: "Touch page 1"; color: theme.muted; font.pixelSize: 13 }
                Item { Layout.fillHeight: true }
            }
        }
    }
}
