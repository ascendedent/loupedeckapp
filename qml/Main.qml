import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    id: root
    visible: true
    width: 1180
    height: 760
    title: "Loupedeck Config"
    color: theme.bg

    FileDialog {
        id: imageDialog
        title: "Choose an image for " + backend.selectedLabel
        nameFilters: ["Images (*.png *.jpg *.jpeg *.bmp *.gif)", "All files (*)"]
        onAccepted: backend.setImage(backend.selectedControl, selectedFile)
    }

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
        readonly property color warn: "#e0a54f"
        readonly property int radius: 10
    }

    // small themed push-button used in the top bar
    component ActionButton: Rectangle {
        id: ab
        property string label: ""
        property bool primary: false
        property bool enabledFlag: true
        signal clicked()
        implicitWidth: abText.width + 26; implicitHeight: 34
        radius: theme.radius
        opacity: enabledFlag ? 1.0 : 0.4
        color: primary ? (abHover.hovered ? Qt.lighter(theme.accent, 1.1) : theme.accent)
                       : (abHover.hovered ? theme.cell : theme.panel2)
        border.color: primary ? theme.accent : theme.line
        Text { id: abText; anchors.centerIn: parent; text: ab.label
            color: primary ? "#ffffff" : theme.text; font.pixelSize: 13; font.bold: ab.primary }
        HoverHandler { id: abHover; enabled: ab.enabledFlag }
        TapHandler { enabled: ab.enabledFlag; onTapped: ab.clicked() }
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
                RowLayout {
                    anchors.centerIn: parent; spacing: 8
                    Rectangle { width: 8; height: 8; radius: 4; color: theme.warn
                        visible: backend.dirty }   // unsaved-changes dot
                    Text { text: backend.activeProfile; color: theme.text; font.pixelSize: 13 }
                }
            }

            // save / revert staged edits
            ActionButton {
                label: "Save"; primary: true; enabledFlag: backend.dirty
                onClicked: backend.save()
            }
            ActionButton {
                label: "Revert"; enabledFlag: backend.dirty
                onClicked: backend.revert()
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

        // ---------- RIGHT: profiles + inspector ----------
        Rectangle {
            Layout.preferredWidth: 300; Layout.fillHeight: true
            radius: theme.radius; color: theme.panel; border.color: theme.line
            ColumnLayout {
                anchors.fill: parent; anchors.margins: 12; spacing: 10
                Text { text: "Profiles"; color: theme.text; font.pixelSize: 15; font.bold: true }
                ListView {
                    Layout.fillWidth: true; Layout.preferredHeight: 150; clip: true; spacing: 4
                    model: backend.profiles
                    delegate: Rectangle {
                        width: ListView.view.width; height: 36; radius: theme.radius
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

                // -------- Inspector --------
                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        text: backend.selectedControl === "" ? "Inspector" : backend.selectedLabel
                        color: theme.text; font.pixelSize: 15; font.bold: true
                        Layout.fillWidth: true; elide: Text.ElideRight
                    }
                    Rectangle {
                        visible: backend.selectedControl !== ""
                        width: 22; height: 22; radius: 11
                        color: clear.hovered ? theme.cell : theme.panel2; border.color: theme.line
                        Text { anchors.centerIn: parent; text: "✕"; color: theme.muted; font.pixelSize: 12 }
                        HoverHandler { id: clear }
                        TapHandler { onTapped: backend.deselect() }
                    }
                }

                Text {
                    visible: backend.selectedControl === ""
                    Layout.fillWidth: true; wrapMode: Text.WordWrap
                    text: "Tap a key, encoder, dial, wheel or button on the device to bind an action or set an image."
                    color: theme.muted; font.pixelSize: 12
                }

                // copy / paste this control's function onto a compatible one
                RowLayout {
                    visible: backend.selectedControl !== ""
                    Layout.fillWidth: true; spacing: 8
                    ActionButton { label: "Copy"; onClicked: backend.copyControl() }
                    ActionButton {
                        label: "Paste"; enabledFlag: backend.canPaste
                        onClicked: backend.pasteControl()
                    }
                    Item { Layout.fillWidth: true }
                }
                Text {
                    visible: backend.selectedControl !== "" && backend.hasClipboard
                    Layout.fillWidth: true; elide: Text.ElideRight
                    text: "Clipboard: " + backend.clipboardLabel
                        + (backend.canPaste ? "" : " (incompatible)")
                    color: backend.canPaste ? theme.ok : theme.muted; font.pixelSize: 11
                }

                // scrollable editor body
                Flickable {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    visible: backend.selectedControl !== ""
                    clip: true; contentHeight: editor.height
                    ColumnLayout {
                        id: editor
                        width: parent.width; spacing: 12

                        // action slots (1 for most controls, 3 for encoder/dial)
                        Repeater {
                            model: backend.selectedSlots
                            delegate: ColumnLayout {
                                required property var modelData
                                Layout.fillWidth: true; spacing: 4
                                Text { text: modelData.label; color: theme.muted; font.pixelSize: 12 }
                                ComboBox {
                                    id: typeBox
                                    Layout.fillWidth: true
                                    model: backend.actionTypes
                                    currentIndex: Math.max(0, backend.actionTypes.indexOf(modelData.type))
                                    onActivated: backend.setActionSlot(modelData.slot, currentText, valueField.text)
                                }
                                TextField {
                                    id: valueField
                                    Layout.fillWidth: true
                                    enabled: typeBox.currentText !== "none"
                                    text: modelData.value
                                    color: theme.text
                                    placeholderText: typeBox.currentText === "hotkey" ? "e.g. ctrl+c"
                                                   : typeBox.currentText === "media" ? "play-pause / next / previous"
                                                   : typeBox.currentText === "text" ? "text to type"
                                                   : "command to run"
                                    placeholderTextColor: theme.muted
                                    background: Rectangle {
                                        radius: 6; color: theme.panel2
                                        border.color: valueField.activeFocus ? theme.accent : theme.line
                                    }
                                    onEditingFinished: backend.setActionSlot(modelData.slot, typeBox.currentText, text)
                                }
                            }
                        }

                        // image section (touch keys / side cells / wheel)
                        ColumnLayout {
                            visible: backend.selectedHasImage
                            Layout.fillWidth: true; spacing: 6
                            Rectangle { Layout.fillWidth: true; height: 1; color: theme.line }
                            Text { text: "Image"; color: theme.muted; font.pixelSize: 12 }
                            Rectangle {
                                Layout.alignment: Qt.AlignHCenter
                                width: 90; height: 90; radius: 8
                                color: theme.panel2; border.color: theme.line
                                Image {
                                    anchors.fill: parent; anchors.margins: 3
                                    source: backend.selectedImage; visible: source != ""
                                    fillMode: Image.PreserveAspectFit; asynchronous: true
                                }
                                Text {
                                    anchors.centerIn: parent; visible: backend.selectedImage == ""
                                    text: "none"; color: theme.muted; font.pixelSize: 11
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 8
                                Button {
                                    Layout.fillWidth: true; text: "Set image…"
                                    onClicked: imageDialog.open()
                                }
                                Button {
                                    text: "Clear"; enabled: backend.selectedImage != ""
                                    onClicked: backend.clearImage(backend.selectedControl)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
