import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtQuick.Dialogs

ApplicationWindow {
    id: root
    visible: true
    width: 1180
    height: 760
    minimumWidth: 900
    minimumHeight: 600
    title: "Loupedeck Config"
    color: theme.bg

    FileDialog {
        id: imageDialog
        title: "Choose an image for " + backend.selectedLabel
        nameFilters: ["Images (*.png *.jpg *.jpeg *.bmp *.gif)", "All files (*)"]
        onAccepted: backend.setImage(backend.selectedControl, selectedFile)
    }

    ColorDialog {
        id: ledDialog
        title: "LED colour for " + backend.selectedLabel
        onAccepted: backend.setLed(backend.selectedControl, selectedColor.toString())
    }

    ColorDialog {
        id: bgDialog
        title: "Background colour for " + backend.selectedLabel
        onAccepted: backend.setBg(backend.selectedControl, selectedColor.toString())
    }

    ColorDialog {
        id: barDialog
        title: "Label bar colour for " + backend.selectedLabel
        onAccepted: backend.setLabel(backend.selectedControl, labelField.text,
            labelPos.currentText, labelMode.currentText, selectedColor.toString())
    }

    // ---- profile name prompt ---------------------------------------------
    // mode: "create" | "duplicate" | "rename"
    Dialog {
        id: nameDialog
        property string mode: "create"
        property string source: ""
        anchors.centerIn: parent
        modal: true
        width: 380
        title: mode === "create" ? "New profile"
             : mode === "duplicate" ? "Duplicate '" + source + "'"
             : "Rename '" + source + "'"
        standardButtons: Dialog.Ok | Dialog.Cancel

        onOpened: { nameField.text = mode === "rename" ? source : ""; nameField.forceActiveFocus() }
        onAccepted: {
            if (nameDialog.mode === "create") backend.createProfile(nameField.text)
            else if (nameDialog.mode === "duplicate") backend.duplicateProfile(nameDialog.source, nameField.text)
            else backend.renameProfile(nameDialog.source, nameField.text)
        }

        ColumnLayout {
            width: parent.width
            spacing: 6
            TextField {
                id: nameField
                Layout.fillWidth: true
                placeholderText: "Profile name"
                color: theme.text
                placeholderTextColor: theme.muted
                background: Rectangle {
                    radius: 6; color: theme.panel2
                    border.color: nameField.activeFocus ? theme.accent : theme.line
                }
                onAccepted: if (nameDialog.standardButton(Dialog.Ok).enabled) nameDialog.accept()
            }
            Text {
                Layout.fillWidth: true
                // rename to the same name is a no-op, not an error
                text: (nameDialog.mode === "rename" && nameField.text === nameDialog.source)
                      ? "" : backend.validateProfileName(nameField.text)
                color: theme.warn; font.pixelSize: 11; wrapMode: Text.WordWrap
                visible: text !== ""
            }
        }

        // block OK while the name is unusable
        Component.onCompleted: syncOk()
        function syncOk() {
            var b = standardButton(Dialog.Ok)
            if (!b) return
            var same = nameDialog.mode === "rename" && nameField.text === nameDialog.source
            b.enabled = !same && backend.validateProfileName(nameField.text) === ""
        }
        Connections { target: nameField; function onTextChanged() { nameDialog.syncOk() } }
    }

    Dialog {
        id: deleteDialog
        property string target: ""
        anchors.centerIn: parent
        modal: true
        title: "Delete profile"
        standardButtons: Dialog.Yes | Dialog.No
        onAccepted: backend.deleteProfile(deleteDialog.target)
        Text {
            text: "Delete '" + deleteDialog.target + "'?\n"
                  + "The file is removed and any app bindings to it are dropped."
            color: theme.text; font.pixelSize: 12; wrapMode: Text.WordWrap
        }
    }

    // ---- hotkey capture ---------------------------------------------------
    // set to a slot key to record the next key combo into that slot's hotkey
    property string recordSlot: ""

    // Qt key event -> input_backend combo string (e.g. "ctrl+shift+c"); "" for a
    // lone modifier or an unmappable key (recording waits for a real key).
    function keyComboFromEvent(event) {
        var k = event.key
        if (k === Qt.Key_Control || k === Qt.Key_Shift || k === Qt.Key_Alt
            || k === Qt.Key_Meta || k === Qt.Key_AltGr
            || k === Qt.Key_Super_L || k === Qt.Key_Super_R)
            return ""
        var name = root.keyName(k, event.text)
        if (name === "")
            return ""
        var mods = []
        if (event.modifiers & Qt.ControlModifier) mods.push("ctrl")
        if (event.modifiers & Qt.AltModifier) mods.push("alt")
        if (event.modifiers & Qt.ShiftModifier) mods.push("shift")
        if (event.modifiers & Qt.MetaModifier) mods.push("super")
        mods.push(name)
        return mods.join("+")
    }

    function keyName(k, text) {
        if (k >= Qt.Key_A && k <= Qt.Key_Z) return String.fromCharCode(k).toLowerCase()
        if (k >= Qt.Key_0 && k <= Qt.Key_9) return String.fromCharCode(k)
        if (k >= Qt.Key_F1 && k <= Qt.Key_F12) return "f" + (k - Qt.Key_F1 + 1)
        switch (k) {
            case Qt.Key_Return: case Qt.Key_Enter: return "enter"
            case Qt.Key_Escape: return "esc"
            case Qt.Key_Tab: return "tab"
            case Qt.Key_Space: return "space"
            case Qt.Key_Backspace: return "backspace"
            case Qt.Key_Delete: return "delete"
            case Qt.Key_Insert: return "insert"
            case Qt.Key_Home: return "home"
            case Qt.Key_End: return "end"
            case Qt.Key_PageUp: return "pageup"
            case Qt.Key_PageDown: return "pagedown"
            case Qt.Key_Up: return "up"
            case Qt.Key_Down: return "down"
            case Qt.Key_Left: return "left"
            case Qt.Key_Right: return "right"
            case Qt.Key_Comma: return "comma"
            case Qt.Key_Period: return "dot"
            case Qt.Key_Slash: return "slash"
            case Qt.Key_Backslash: return "backslash"
            case Qt.Key_Semicolon: return "semicolon"
            case Qt.Key_Apostrophe: return "apostrophe"
            case Qt.Key_Minus: return "minus"
            case Qt.Key_Equal: return "equal"
            case Qt.Key_BracketLeft: return "leftbrace"
            case Qt.Key_BracketRight: return "rightbrace"
            case Qt.Key_QuoteLeft: return "grave"
        }
        if (text && text.length === 1) {
            var c = text.toLowerCase()
            if ((c >= "a" && c <= "z") || (c >= "0" && c <= "9")) return c
        }
        return ""
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
        HoverHandler { id: abHover; enabled: ab.enabledFlag; cursorShape: Qt.PointingHandCursor }
        TapHandler { id: abTap; enabled: ab.enabledFlag; onTapped: ab.clicked() }
        scale: abTap.pressed ? 0.94 : 1.0
        Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
        Behavior on color { ColorAnimation { duration: 110 } }
        Behavior on opacity { NumberAnimation { duration: 130 } }
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

    // subtle gradient backdrop behind the body
    Rectangle {
        anchors.fill: parent; z: -1
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#191922" }
            GradientStop { position: 1.0; color: "#101015" }
        }
    }

    // hotkey recorder: grabs focus and captures the next combo into recordSlot
    Rectangle {
        id: recordOverlay
        anchors.fill: parent; z: 100
        visible: root.recordSlot !== ""
        color: Qt.rgba(0, 0, 0, 0.62)
        focus: visible
        onVisibleChanged: if (visible) forceActiveFocus()
        Keys.onPressed: (event) => {
            if (event.key === Qt.Key_Escape) { root.recordSlot = ""; event.accepted = true; return }
            var combo = root.keyComboFromEvent(event)
            if (combo !== "") {
                backend.setActionSlot(root.recordSlot, "hotkey", combo)
                root.recordSlot = ""
                event.accepted = true
            }
        }
        MouseArea { anchors.fill: parent; onClicked: root.recordSlot = "" }  // click outside cancels
        Rectangle {
            anchors.centerIn: parent; width: 340; height: 130; radius: theme.radius
            color: theme.panel; border.color: theme.accent
            ColumnLayout {
                anchors.centerIn: parent; spacing: 10
                Rectangle {
                    Layout.alignment: Qt.AlignHCenter
                    width: 14; height: 14; radius: 7; color: theme.warn
                }
                Text { text: "Press a key combination…"; color: theme.text
                    font.pixelSize: 16; font.bold: true; Layout.alignment: Qt.AlignHCenter }
                Text { text: "Modifiers optional · Esc or click to cancel"; color: theme.muted
                    font.pixelSize: 12; Layout.alignment: Qt.AlignHCenter }
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
                Text {
                    text: "Drag an action onto a control"; color: theme.muted; font.pixelSize: 11
                }
                ListView {
                    id: libList
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 4
                    model: backend.actionLibrary
                    section.property: "category"
                    section.delegate: Text {
                        width: libList.width; topPadding: 8; bottomPadding: 2
                        text: section.toUpperCase(); color: theme.muted
                        font.pixelSize: 10; font.bold: true; font.letterSpacing: 1
                    }
                    delegate: Rectangle {
                        id: tile
                        required property var modelData
                        width: libList.width; height: 38; radius: theme.radius
                        // transparent while dragging so it never covers a drop target;
                        // the compact chip below is the only thing shown then
                        color: dragMa.drag.active ? "transparent"
                             : (tileHover.hovered ? theme.cell : theme.panel2)
                        border.color: dragMa.drag.active ? "transparent" : theme.line
                        Behavior on color { ColorAnimation { duration: 120 } }

                        // drag payload read by the DropArea on each control
                        property string aType: modelData.type
                        property string aValue: modelData.value
                        property string aLabel: modelData.label
                        // grab point within the tile; the Drag hit point is pinned here so
                        // it tracks the CURSOR (not the tile centre) on small controls
                        property point grab: Qt.point(width / 2, height / 2)

                        Drag.active: dragMa.drag.active
                        Drag.source: tile

                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 10; anchors.rightMargin: 10; spacing: 8
                            visible: !dragMa.drag.active
                            Rectangle { width: 18; height: 18; radius: 4; color: theme.accent; opacity: 0.85 }
                            Text { text: tile.modelData.label; color: theme.text; font.pixelSize: 13
                                Layout.fillWidth: true; elide: Text.ElideRight }
                            Text { text: tile.modelData.type; color: theme.muted; font.pixelSize: 10 }
                        }

                        // compact ghost floating just above the cursor while dragging
                        Rectangle {
                            visible: dragMa.drag.active
                            width: chipText.implicitWidth + 24; height: 26; radius: 13
                            color: theme.accent
                            x: tile.grab.x - width / 2
                            y: tile.grab.y - height - 16
                            Text { id: chipText; anchors.centerIn: parent; text: tile.modelData.label
                                color: "white"; font.pixelSize: 12; font.bold: true }
                        }

                        HoverHandler { id: tileHover }
                        MouseArea {
                            id: dragMa
                            anchors.fill: parent
                            cursorShape: Qt.OpenHandCursor
                            drag.target: tile
                            onPressed: (mouse) => {
                                tile.grab = Qt.point(mouse.x, mouse.y)
                                tile.Drag.hotSpot = tile.grab   // hit-test at the cursor
                            }
                            onReleased: tile.Drag.drop()
                        }
                        // float above the other panels while dragging, snap back after
                        states: State {
                            when: dragMa.drag.active
                            ParentChange { target: tile; parent: root.contentItem }
                        }
                    }
                }
            }
        }

        // ---------- CENTER: device view ----------
        Rectangle {
            id: centerPanel
            Layout.fillWidth: true; Layout.fillHeight: true
            Layout.minimumWidth: 320
            radius: theme.radius; color: theme.panel; border.color: theme.line
            clip: true
            DeviceView {
                id: deviceView
                anchors.centerIn: parent
                theme: theme
                // shrink to fit the panel (never upscale) so it never spills
                // over the side panels when the window is resized
                scale: Math.min(1,
                    (centerPanel.width - 28) / implicitWidth,
                    (centerPanel.height - 28) / implicitHeight)
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
                        Behavior on color { ColorAnimation { duration: 120 } }
                        HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                        TapHandler { onTapped: backend.loadProfile(modelData) }
                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: 10; spacing: 8
                            Text { text: "▦"; color: theme.muted; font.pixelSize: 14 }
                            Text { text: modelData; color: theme.text; font.pixelSize: 13; Layout.fillWidth: true; elide: Text.ElideRight }
                        }
                    }
                }

                // Flow, not RowLayout: four buttons do not fit the 300px panel
                // on one line, and a RowLayout pushed the whole column wider
                // than its parent instead of wrapping.
                Flow {
                    Layout.fillWidth: true
                    spacing: 6
                    ActionButton {
                        label: "New"
                        onClicked: { nameDialog.mode = "create"; nameDialog.open() }
                    }
                    ActionButton {
                        label: "Duplicate"
                        enabledFlag: backend.activeProfile !== "(none)"
                        onClicked: {
                            nameDialog.mode = "duplicate"
                            nameDialog.source = backend.activeProfile
                            nameDialog.open()
                        }
                    }
                    ActionButton {
                        label: "Rename"
                        enabledFlag: backend.activeProfile !== "(none)"
                        onClicked: {
                            nameDialog.mode = "rename"
                            nameDialog.source = backend.activeProfile
                            nameDialog.open()
                        }
                    }
                    ActionButton {
                        label: "Delete"
                        // never delete the last profile: nothing would be left to load
                        enabledFlag: backend.activeProfile !== "(none)" && backend.profiles.length > 1
                        onClicked: {
                            deleteDialog.target = backend.activeProfile
                            deleteDialog.open()
                        }
                    }
                }

                // -------- Dynamic mode: focused app -> profile --------
                Rectangle { Layout.fillWidth: true; height: 1; color: theme.line }
                ColumnLayout {
                    Layout.fillWidth: true; spacing: 6

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "App bindings"; color: theme.muted; font.pixelSize: 12
                            Layout.fillWidth: true
                        }
                        Text {
                            text: backend.dynamicMode ? "on" : "off"
                            color: backend.dynamicMode ? theme.ok : theme.muted
                            font.pixelSize: 11
                        }
                    }

                    // Binds whatever window is focused *now*, so the button has
                    // to say what that is before you press it.
                    ActionButton {
                        Layout.fillWidth: true
                        label: backend.focusedApp === ""
                               ? "No focused app detected"
                               : "Bind " + backend.focusedApp + " → " + backend.activeProfile
                        enabledFlag: backend.focusedApp !== ""
                        onClicked: backend.bindFocusedApp(backend.activeProfile)
                    }

                    Text {
                        Layout.fillWidth: true
                        visible: backend.appBindings.length === 0
                        text: "No apps bound yet. Focus an app, then bind it to the "
                              + "profile you want it to use."
                        color: theme.muted; font.pixelSize: 11; wrapMode: Text.WordWrap
                    }

                    ListView {
                        Layout.fillWidth: true
                        Layout.preferredHeight: Math.min(contentHeight, 110)
                        visible: backend.appBindings.length > 0
                        clip: true; spacing: 3
                        model: backend.appBindings
                        delegate: Rectangle {
                            required property var modelData
                            width: ListView.view.width; height: 28
                            radius: 6; color: theme.panel2
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 8; anchors.rightMargin: 4
                                spacing: 6
                                Text {
                                    text: modelData.app; color: theme.text
                                    font.pixelSize: 11; Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }
                                Text {
                                    text: "→ " + modelData.profile; color: theme.muted
                                    font.pixelSize: 11; elide: Text.ElideRight
                                    Layout.maximumWidth: 90
                                }
                                Text {
                                    text: "✕"; color: rm.hovered ? theme.text : theme.muted
                                    font.pixelSize: 12; rightPadding: 6
                                    HoverHandler { id: rm; cursorShape: Qt.PointingHandCursor }
                                    TapHandler { onTapped: backend.removeBinding(modelData.app) }
                                }
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true; spacing: 6
                        visible: backend.appBindings.length > 0
                        Text {
                            text: "Fallback"; color: theme.muted; font.pixelSize: 11
                        }
                        ComboBox {
                            Layout.fillWidth: true
                            model: backend.profiles
                            currentIndex: backend.profiles.indexOf(backend.defaultProfile)
                            displayText: backend.defaultProfile === ""
                                         ? "none" : backend.defaultProfile
                            onActivated: backend.setDefaultProfile(backend.profiles[currentIndex])
                        }
                    }
                }

                Rectangle { Layout.fillWidth: true; height: 1; color: theme.line }

                // -------- Inspector --------
                RowLayout {
                    Layout.fillWidth: true
                    ActionButton {
                        visible: backend.menuDepth > 0
                        label: "← Back"
                        onClicked: backend.goBack()
                    }
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
                                    model: backend.selectedActionTypes
                                    currentIndex: Math.max(0, backend.selectedActionTypes.indexOf(modelData.type))
                                    onActivated: backend.setActionSlot(modelData.slot, currentText, valueField.text)
                                }
                                // Fixed-choice values (scroll direction, media
                                // transport) pick from a list; free text is for
                                // the types that genuinely take arbitrary input.
                                ComboBox {
                                    id: choiceBox
                                    Layout.fillWidth: true
                                    visible: !!backend.valueOptions[typeBox.currentText]
                                    textRole: "label"
                                    model: backend.valueOptions[typeBox.currentText] || []
                                    currentIndex: {
                                        var opts = backend.valueOptions[typeBox.currentText] || []
                                        for (var i = 0; i < opts.length; i++)
                                            if (opts[i].value === modelData.value)
                                                return i
                                        return 0
                                    }
                                    onActivated: {
                                        var opts = backend.valueOptions[typeBox.currentText] || []
                                        if (opts[currentIndex])
                                            backend.setActionSlot(modelData.slot,
                                                                  typeBox.currentText,
                                                                  opts[currentIndex].value)
                                    }
                                }
                                TextField {
                                    id: valueField
                                    Layout.fillWidth: true
                                    visible: typeBox.currentText !== "none"
                                             && typeBox.currentText !== "back"
                                             && !backend.valueOptions[typeBox.currentText]
                                    text: modelData.value
                                    color: theme.text
                                    placeholderText: typeBox.currentText === "hotkey" ? "e.g. ctrl+c"
                                                   : typeBox.currentText === "media" ? "play-pause / next / previous"
                                                   : typeBox.currentText === "scroll" ? "up / down / left / right"
                                                   : typeBox.currentText === "text" ? "text to type"
                                                   : typeBox.currentText === "submenu" ? "submenu name"
                                                   : "command to run"
                                    placeholderTextColor: theme.muted
                                    background: Rectangle {
                                        radius: 6; color: theme.panel2
                                        border.color: valueField.activeFocus ? theme.accent : theme.line
                                    }
                                    onEditingFinished: backend.setActionSlot(modelData.slot, typeBox.currentText, text)
                                }
                                // hotkey helpers: record a live combo or pick a known one
                                RowLayout {
                                    visible: typeBox.currentText === "hotkey"
                                    Layout.fillWidth: true; spacing: 8
                                    ActionButton {
                                        label: "⏺ Record"
                                        onClicked: root.recordSlot = modelData.slot
                                    }
                                    ComboBox {
                                        id: presetBox
                                        Layout.fillWidth: true
                                        textRole: "label"
                                        // common shortcuts first, then this machine's configured ones
                                        model: backend.commonHotkeys.concat(backend.systemShortcuts)
                                        displayText: "Presets…"
                                        onActivated: {
                                            var item = model[currentIndex]
                                            if (item) backend.setActionSlot(modelData.slot, "hotkey", item.value)
                                        }
                                    }
                                }
                                // navigate into a submenu to edit its keys
                                ActionButton {
                                    visible: typeBox.currentText === "submenu" && backend.selectedIsSubmenu
                                    label: "Open submenu →"
                                    onClicked: backend.enterSubmenu()
                                }
                            }
                        }

                        // image section (touch keys / side cells / wheel)
                        ColumnLayout {
                            visible: backend.selectedHasImage
                            Layout.fillWidth: true; spacing: 6
                            Rectangle { Layout.fillWidth: true; height: 1; color: theme.line }
                            Text { text: "Image"; color: theme.muted; font.pixelSize: 12 }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 10
                                Rectangle {
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
                                // helper: the exact device size to make a source
                                // image (it's fit, never cropped or stretched)
                                ColumnLayout {
                                    Layout.fillWidth: true; spacing: 4
                                    Text {
                                        visible: backend.selectedImageDims !== ""
                                        Layout.fillWidth: true; wrapMode: Text.WordWrap
                                        text: "Best size: " + backend.selectedImageDims
                                        color: theme.text; font.pixelSize: 12; font.bold: true
                                    }
                                    Text {
                                        Layout.fillWidth: true; wrapMode: Text.WordWrap
                                        text: "Images are scaled to fit, never cropped or stretched. Match this size for a pixel-perfect fill."
                                        color: theme.muted; font.pixelSize: 10
                                    }
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

                            // ---- text label (on by default; uncheck to hide) ----
                            Rectangle { Layout.fillWidth: true; height: 1; color: theme.line }
                            RowLayout {
                                Layout.fillWidth: true
                                Text { text: "Label"; color: theme.muted; font.pixelSize: 12
                                    Layout.fillWidth: true; verticalAlignment: Text.AlignVCenter }
                                CheckBox {
                                    id: labelShow
                                    text: "Show"
                                    checked: backend.selectedLabelEnabled
                                    onToggled: backend.setLabelEnabled(backend.selectedControl, checked)
                                    contentItem: Text {
                                        text: labelShow.text; color: theme.text; font.pixelSize: 12
                                        leftPadding: labelShow.indicator.width + 6
                                        verticalAlignment: Text.AlignVCenter
                                    }
                                }
                            }
                            TextField {
                                id: labelField
                                Layout.fillWidth: true
                                enabled: backend.selectedLabelEnabled
                                opacity: enabled ? 1.0 : 0.45
                                text: backend.selectedLabelText
                                color: theme.text
                                placeholderText: "label text (blank = auto from action)"
                                placeholderTextColor: theme.muted
                                background: Rectangle {
                                    radius: 6; color: theme.panel2
                                    border.color: labelField.activeFocus ? theme.accent : theme.line
                                }
                                onEditingFinished: backend.setLabel(backend.selectedControl,
                                    text, labelPos.currentText, labelMode.currentText,
                                    backend.selectedLabelBarColor)
                            }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 8
                                enabled: backend.selectedLabelEnabled
                                opacity: enabled ? 1.0 : 0.45
                                ComboBox {
                                    id: labelPos
                                    Layout.fillWidth: true
                                    model: backend.labelPositions
                                    currentIndex: Math.max(0, backend.labelPositions.indexOf(backend.selectedLabelPos))
                                    onActivated: backend.setLabel(backend.selectedControl,
                                        labelField.text, currentText, labelMode.currentText,
                                        backend.selectedLabelBarColor)
                                }
                                ComboBox {
                                    id: labelMode
                                    Layout.fillWidth: true
                                    // shrink only makes sense for a top/bottom band, not middle
                                    property var modes: labelPos.currentText === "middle"
                                        ? ["over", "bar"] : backend.labelModes
                                    model: modes
                                    currentIndex: Math.max(0, modes.indexOf(backend.selectedLabelMode))
                                    onActivated: backend.setLabel(backend.selectedControl,
                                        labelField.text, labelPos.currentText, currentText,
                                        backend.selectedLabelBarColor)
                                }
                            }
                            // ---- label bar colour (bar / shrink modes) ----
                            RowLayout {
                                visible: labelMode.currentText === "bar" || labelMode.currentText === "shrink"
                                enabled: backend.selectedLabelEnabled
                                opacity: enabled ? 1.0 : 0.45
                                Layout.fillWidth: true; spacing: 8
                                Text { text: "Bar colour"; color: theme.muted; font.pixelSize: 12
                                    Layout.alignment: Qt.AlignVCenter }
                                Rectangle {
                                    width: 34; height: 22; radius: 6
                                    color: backend.selectedLabelBarColor !== "" ? backend.selectedLabelBarColor : theme.panel2
                                    border.color: theme.line
                                }
                                Button { text: "Pick…"; onClicked: barDialog.open() }
                                Button {
                                    text: "Reset"; enabled: backend.selectedLabelBarColor !== ""
                                    onClicked: backend.setLabel(backend.selectedControl, labelField.text,
                                        labelPos.currentText, labelMode.currentText, "")
                                }
                                Item { Layout.fillWidth: true }
                            }

                            // ---- background colour (image-bearing controls) ----
                            Rectangle { Layout.fillWidth: true; height: 1; color: theme.line }
                            Text { text: "Background colour"; color: theme.muted; font.pixelSize: 12 }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 8
                                Rectangle {
                                    width: 40; height: 26; radius: 6
                                    color: backend.selectedBg !== "" ? backend.selectedBg : theme.panel2
                                    border.color: theme.line
                                }
                                Button { Layout.fillWidth: true; text: "Pick…"; onClicked: bgDialog.open() }
                                Button {
                                    text: "Off"; enabled: backend.selectedBg !== ""
                                    onClicked: backend.setBg(backend.selectedControl, "")
                                }
                            }
                        }

                        // LED colour (physical buttons: workspace + CT buttons)
                        ColumnLayout {
                            visible: backend.selectedHasLed
                            Layout.fillWidth: true; spacing: 6
                            Rectangle { Layout.fillWidth: true; height: 1; color: theme.line }
                            Text { text: "LED colour"; color: theme.muted; font.pixelSize: 12 }
                            RowLayout {
                                Layout.fillWidth: true; spacing: 8
                                Rectangle {
                                    width: 40; height: 26; radius: 6
                                    color: backend.selectedLed !== "" ? backend.selectedLed : theme.panel2
                                    border.color: theme.line
                                }
                                Button {
                                    Layout.fillWidth: true; text: "Pick…"
                                    onClicked: ledDialog.open()
                                }
                                Button {
                                    text: "Off"; enabled: backend.selectedLed !== ""
                                    onClicked: backend.setLed(backend.selectedControl, "")
                                }
                            }
                        }

                        // Encoder feel (rotate controls: encoders + CT dial)
                        ColumnLayout {
                            id: tuningSection
                            visible: backend.selectedHasTuning
                            Layout.fillWidth: true; spacing: 6

                            // The dropdown is index-based, so map to and from the
                            // preset id the backend speaks. An empty selectedPreset
                            // means a hand-edited combination no preset covers; the
                            // dropdown then shows nothing rather than lying.
                            function presetIndex(id) {
                                for (var i = 0; i < backend.tuningPresets.length; i++)
                                    if (backend.tuningPresets[i].id === id)
                                        return i
                                return -1
                            }

                            // Whatever speed is showing, so the checkboxes can
                            // resend it without changing it.
                            function currentPresetId() {
                                var i = presetBox.currentIndex
                                return i >= 0 && i < backend.tuningPresets.length
                                    ? backend.tuningPresets[i].id : "original"
                            }

                            Rectangle { Layout.fillWidth: true; height: 1; color: theme.line }
                            Text { text: "Encoder feel"; color: theme.muted; font.pixelSize: 12 }

                            RowLayout {
                                Layout.fillWidth: true; spacing: 8
                                Text {
                                    text: "Speed"; color: theme.muted
                                    font.pixelSize: 12; Layout.preferredWidth: 46
                                }
                                ComboBox {
                                    id: presetBox
                                    Layout.fillWidth: true
                                    model: backend.tuningPresets
                                    textRole: "label"
                                    currentIndex: tuningSection.presetIndex(backend.selectedPreset)
                                    onActivated: backend.setTuning(
                                        backend.tuningPresets[currentIndex].id,
                                        invertBox.checked, accelBox.checked)
                                }
                            }

                            CheckBox {
                                id: invertBox
                                text: "Invert direction"
                                checked: backend.selectedInvert
                                onToggled: backend.setTuning(
                                    tuningSection.currentPresetId(), checked,
                                    accelBox.checked)
                            }

                            CheckBox {
                                id: accelBox
                                text: "Accelerate when spun"
                                checked: backend.selectedAccel
                                onToggled: backend.setTuning(
                                    tuningSection.currentPresetId(),
                                    invertBox.checked, checked)
                            }

                            Text {
                                Layout.fillWidth: true
                                text: backend.selectedTuningSummary
                                color: theme.muted; font.pixelSize: 11
                                wrapMode: Text.WordWrap
                            }
                        }
                    }
                }
            }
        }
    }
}
