import QtQml
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

    // ---- keyboard shortcuts ----------------------------------------------
    // Text fields keep the editing keys: a Shortcut is application-wide, so
    // without this guard Ctrl+C in the search box would copy a device control
    // instead of the text, and Esc would clear the selection instead of the
    // field. TextInput and TextEdit both carry inputMethodComposing; nothing
    // else in the window does.
    readonly property bool typing: root.activeFocusItem !== null
        && root.activeFocusItem.hasOwnProperty("inputMethodComposing")

    Shortcut { sequences: [StandardKey.Save]; onActivated: if (backend.dirty) backend.save() }
    Shortcut { sequence: "Ctrl+R"; onActivated: if (backend.dirty) backend.revert() }
    Shortcut { sequences: [StandardKey.Find]; onActivated: librarySearch.forceActiveFocus() }
    Shortcut {
        sequences: [StandardKey.Copy]; enabled: !root.typing
        onActivated: if (backend.selectedControl !== "") backend.copyControl()
    }
    Shortcut {
        sequences: [StandardKey.Paste]; enabled: !root.typing && backend.canPaste
        onActivated: backend.pasteControl()
    }
    Shortcut {
        sequences: [StandardKey.Cancel]; enabled: !root.typing
        onActivated: backend.menuDepth > 0 ? backend.goBack() : backend.deselect()
    }
    // Ctrl+1..8 puts a workspace on the device, so editing workspace 5 does not
    // mean reaching over to press the physical button. Instantiator rather than
    // Repeater because a Shortcut is not an Item and has nothing to be laid out
    // in; the count follows the model, so a Live S gets four of these.
    Instantiator {
        model: backend.workspaceButtons
        delegate: Shortcut {
            required property int index
            required property string modelData
            sequence: "Ctrl+" + (index + 1)
            onActivated: backend.showWorkspace(modelData)
        }
    }

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

    Dialog {
        id: wsNameDialog
        anchors.centerIn: Overlay.overlay
        modal: true
        width: 360
        title: "Name this workspace"
        standardButtons: Dialog.Ok | Dialog.Cancel
        onOpened: { wsNameField.text = backend.workspaceName; wsNameField.forceActiveFocus() }
        onAccepted: backend.setWorkspaceName(backend.selectedWs, wsNameField.text)
        ColumnLayout {
            width: parent.width
            spacing: 8
            TextField {
                id: wsNameField
                objectName: "wsNameField"
                Layout.fillWidth: true
                placeholderText: "Streaming, Editing, ..."
                onAccepted: wsNameDialog.accept()
            }
            Text {
                Layout.fillWidth: true
                text: "Leave blank to go back to the number. Saved with the profile."
                color: theme.muted; font.pixelSize: 11; wrapMode: Text.WordWrap
            }
        }
    }

    // ---- import / export --------------------------------------------------
    property string ioError: ""

    FileDialog {
        id: exportDialog
        title: "Export '" + backend.activeProfile + "'"
        fileMode: FileDialog.SaveFile
        nameFilters: ["Loupedeck profile (*.json)", "All files (*)"]
        currentFile: "file:" + backend.activeProfile + ".json"
        onAccepted: root.ioError = backend.exportProfile(backend.activeProfile, selectedFile)
    }

    FileDialog {
        id: importDialog
        title: "Import a profile"
        fileMode: FileDialog.OpenFile
        nameFilters: ["Loupedeck profile (*.json)", "All files (*)"]
        onAccepted: root.ioError = backend.importProfile(selectedFile)
    }

    // An import can fail for reasons worth reading (wrong schema, not a
    // profile), so the message is shown rather than only logged.
    Dialog {
        id: ioErrorDialog
        anchors.centerIn: parent
        modal: true
        width: 420
        title: "Import failed"
        standardButtons: Dialog.Ok
        onClosed: root.ioError = ""
        Text {
            text: root.ioError; color: theme.text
            font.pixelSize: 12; wrapMode: Text.WordWrap
        }
    }

    onIoErrorChanged: if (ioError !== "") ioErrorDialog.open()

    // ---- unsaved-changes guard -------------------------------------------
    // Every action that would throw away a draft routes through withDraftCheck,
    // so there is one place deciding what happens rather than a dialog bolted
    // onto each call site.
    Dialog {
        id: discardDialog
        property var pending: null
        anchors.centerIn: parent
        modal: true
        width: 400
        title: "Unsaved changes"
        standardButtons: Dialog.Save | Dialog.Discard | Dialog.Cancel

        function run() {
            var fn = pending
            pending = null
            if (fn) fn()
        }
        onAccepted: { backend.save(); run() }        // Save
        onDiscarded: { backend.revert(); run() }     // Discard
        onRejected: pending = null                   // Cancel

        Text {
            text: "'" + backend.activeProfile + "' has changes that are not saved."
            color: theme.text; font.pixelSize: 12; wrapMode: Text.WordWrap
        }
    }

    function withDraftCheck(fn) {
        if (!backend.dirty) { fn(); return }
        discardDialog.pending = fn
        discardDialog.open()
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

    // Closing with a draft open would discard it with no warning at all.
    // Unless it is not being discarded: with close-to-tray on, the window is
    // only being hidden, the draft is still there, and a prompt would be an
    // interruption asking about nothing.
    property bool forceClose: false
    // A quit was asked for (tray menu), as opposed to the window being closed.
    // Closing the window with the tray on does not end the app.
    property bool quitting: false
    function reallyQuit() {
        root.forceClose = true
        root.close()
        Qt.quit()
    }
    onClosing: function(close) {
        if (backend.closeToTray && !root.forceClose) {
            close.accepted = false
            root.hide()
            backend.setWindowVisible(false)
            return
        }
        if (backend.dirty && !root.forceClose) {
            close.accepted = false
            closeDialog.open()
        }
    }

    // The tray asks for the window back through here.
    Connections {
        target: backend
        function onWindowShowRequested() {
            root.show()
            root.raise()
            root.requestActivate()
            backend.setWindowVisible(true)
        }
        function onWindowHideRequested() {
            root.hide()
            backend.setWindowVisible(false)
        }
        // The tray asks rather than quits: a draft is still a draft with the
        // window hidden, and there would be nowhere to warn about it.
        function onQuitRequested() {
            root.quitting = true
            if (backend.dirty) {
                root.show()
                root.raise()
                root.requestActivate()
                backend.setWindowVisible(true)
                closeDialog.open()
                return
            }
            root.reallyQuit()
        }
    }

    Dialog {
        id: closeDialog
        objectName: "closeDialog"
        anchors.centerIn: parent
        modal: true
        width: 400
        title: "Unsaved changes"
        standardButtons: Dialog.Save | Dialog.Discard | Dialog.Cancel
        // Reached either by closing the window or by Quit from the tray; only
        // the second one should end the app.
        function finish() {
            if (root.quitting) { root.reallyQuit(); return }
            root.forceClose = true
            root.close()
        }
        onAccepted: { backend.save(); finish() }
        onDiscarded: { backend.revert(); finish() }
        onRejected: root.quitting = false
        Text {
            text: "'" + backend.activeProfile + "' has changes that are not saved."
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
            anchors.leftMargin: 14
            anchors.rightMargin: 14
            spacing: 10

            // device pill
            Rectangle {
                Layout.preferredWidth: 170; Layout.preferredHeight: 34
                Layout.minimumWidth: 110
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

            Rectangle {
                Layout.preferredWidth: 150; Layout.preferredHeight: 34
                Layout.minimumWidth: 90
                radius: theme.radius; color: theme.panel2; border.color: theme.line
                RowLayout {
                    anchors.centerIn: parent; spacing: 8
                    Rectangle { width: 8; height: 8; radius: 4; color: theme.warn
                        visible: backend.dirty }   // unsaved-changes dot
                    Text { text: backend.activeProfile; color: theme.text; font.pixelSize: 13 }
                }
            }

            // Which of the eight workspaces is on the device. Numbered
            // buttons alone say nothing about what is on them, so this shows
            // the name when one has been given and can set one.
            Rectangle {
                Layout.preferredHeight: 34
                Layout.preferredWidth: Math.min(160, wsLabel.implicitWidth + 26)
                Layout.minimumWidth: 80
                radius: theme.radius
                color: wsHover.hovered ? theme.cell : theme.panel2
                border.color: theme.line
                Behavior on color { ColorAnimation { duration: 120 } }
                Text {
                    id: wsLabel
                    anchors.centerIn: parent
                    width: parent.width - 20
                    text: backend.workspaceLabel
                    color: theme.text; font.pixelSize: 13
                    horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
                }
                HoverHandler { id: wsHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: wsNameDialog.open() }
                ToolTip.visible: wsHover.hovered
                ToolTip.text: "Rename this workspace"
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
                // A held dynamic switch is invisible otherwise: the profile simply
            // fails to change and the reason is not on screen anywhere.
            Rectangle {
                visible: backend.pendingProfile !== ""
                Layout.preferredHeight: 26
                Layout.preferredWidth: heldText.width + 20
                radius: theme.radius
                color: theme.panel2
                border.color: theme.warn
                Text {
                    id: heldText
                    anchors.centerIn: parent
                    text: "⏸ " + backend.pendingProfile + " held"
                    color: theme.warn; font.pixelSize: 11
                }
            }

            // No device library: nothing can be enumerated, so the device pill
            // would say "not connected" forever with no way to learn why.
            Rectangle {
                visible: !backend.deviceHealth.ok
                Layout.preferredHeight: 26
                Layout.preferredWidth: devWarn.width + 20
                radius: theme.radius
                color: theme.panel2
                border.color: theme.warn
                Text {
                    id: devWarn
                    anchors.centerIn: parent
                    text: "⚠ device library"
                    color: theme.warn; font.pixelSize: 11
                }
                HoverHandler { id: devHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: deviceDialog.open() }
                ToolTip.visible: devHover.hovered
                ToolTip.text: "Click for the install command"
            }

            Dialog {
                id: deviceDialog
                anchors.centerIn: Overlay.overlay
                modal: true
                width: 460
                title: "Device library missing"
                standardButtons: Dialog.Ok
                ColumnLayout {
                    width: parent.width
                    spacing: 8
                    Text {
                        Layout.fillWidth: true
                        text: backend.deviceHealth.detail
                        color: theme.text; font.pixelSize: 12; wrapMode: Text.WordWrap
                    }
                }
            }

            // Input backend trouble, e.g. ydotoold not running. Without this the
            // failure is invisible: every action silently does nothing.
            Rectangle {
                visible: !backend.inputHealth.ok
                Layout.preferredHeight: 26
                Layout.preferredWidth: inputWarn.width + 20
                radius: theme.radius
                color: theme.panel2
                border.color: theme.warn
                Text {
                    id: inputWarn
                    anchors.centerIn: parent
                    text: "⚠ input"
                    color: theme.warn; font.pixelSize: 11
                }
                HoverHandler { id: inputHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: inputDialog.open() }
                ToolTip.visible: inputHover.hovered
                ToolTip.text: backend.inputHealth.detail
            }

            Dialog {
                id: inputDialog
                anchors.centerIn: Overlay.overlay
                modal: true
                width: 440
                title: "Input is not working"
                standardButtons: Dialog.Ok
                ColumnLayout {
                    width: parent.width
                    spacing: 8
                    Text {
                        Layout.fillWidth: true
                        text: backend.inputHealth.detail
                        color: theme.text; font.pixelSize: 12; wrapMode: Text.WordWrap
                    }
                    Text {
                        Layout.fillWidth: true
                        text: "Actions that send keystrokes will do nothing until this is "
                              + "fixed. See the Troubleshooting section of the README."
                        color: theme.muted; font.pixelSize: 11; wrapMode: Text.WordWrap
                    }
                    ActionButton {
                        label: "Check again"
                        onClicked: backend.recheckInput()
                    }
                }
            }

            // fn layer: which mode, and whether it is engaged right now.
            Rectangle {
                Layout.preferredHeight: 26
                Layout.preferredWidth: fnText.width + 20
                radius: theme.radius
                color: backend.fnLatched ? theme.warn : theme.panel2
                border.color: backend.fnLatched ? theme.warn : theme.line
                Behavior on color { ColorAnimation { duration: 130 } }
                Text {
                    id: fnText
                    anchors.centerIn: parent
                    text: "fn: " + backend.fnMode
                    color: backend.fnLatched ? "#15151b" : theme.muted
                    font.pixelSize: 11
                }
                HoverHandler { id: fnHover; cursorShape: Qt.PointingHandCursor }
                TapHandler { onTapped: fnPopup.open() }
                ToolTip.visible: fnHover.hovered
                ToolTip.text: "fn " + (backend.fnMode === "hold"
                    ? "works while held" : "sticks until pressed again")
                    + ". Click to configure."

                Popup {
                    id: fnPopup
                    y: parent.height + 6
                    width: 260
                    modal: false
                    focus: true
                    background: Rectangle {
                        radius: theme.radius; color: theme.panel
                        border.color: theme.line
                    }
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 8

                        Text {
                            text: "fn layer"; color: theme.text
                            font.pixelSize: 13; font.bold: true
                        }

                        RowLayout {
                            Layout.fillWidth: true; spacing: 6
                            Text {
                                text: "Mode"; color: theme.muted
                                font.pixelSize: 11; Layout.preferredWidth: 60
                            }
                            ComboBox {
                                Layout.fillWidth: true
                                model: ["hold", "latch"]
                                currentIndex: backend.fnMode === "latch" ? 1 : 0
                                onActivated: backend.setFnMode(currentText)
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true; spacing: 6
                            Text {
                                text: "On"; color: theme.muted
                                font.pixelSize: 11; Layout.preferredWidth: 60
                            }
                            Rectangle {
                                width: 34; height: 24; radius: 6
                                color: backend.fnActiveColor !== "" ? backend.fnActiveColor : "#ffffff"
                                border.color: theme.line
                            }
                            ActionButton {
                                Layout.fillWidth: true
                                label: "Pick…"
                                onClicked: fnOnDialog.open()
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true; spacing: 6
                            Text {
                                text: "Off"; color: theme.muted
                                font.pixelSize: 11; Layout.preferredWidth: 60
                            }
                            Rectangle {
                                width: 34; height: 24; radius: 6
                                color: backend.fnInactiveColor !== ""
                                       ? backend.fnInactiveColor : theme.cell
                                border.color: theme.line
                            }
                            ActionButton {
                                Layout.fillWidth: true
                                label: "Pick…"
                                onClicked: fnOffDialog.open()
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: backend.fnInactiveColor === ""
                                  ? "Off uses the button's own LED colour."
                                  : ""
                            visible: text !== ""
                            color: theme.muted; font.pixelSize: 10
                            wrapMode: Text.WordWrap
                        }
                        ActionButton {
                            visible: backend.fnInactiveColor !== ""
                            label: "Use LED colour when off"
                            onClicked: backend.setFnColors(backend.fnActiveColor, "")
                        }
                    }
                }
            }

            ColorDialog {
                id: fnOnDialog
                title: "fn key colour while the layer is on"
                onAccepted: backend.setFnColors(selectedColor.toString(),
                                                backend.fnInactiveColor)
            }
            ColorDialog {
                id: fnOffDialog
                title: "fn key colour while the layer is off"
                onAccepted: backend.setFnColors(backend.fnActiveColor,
                                                selectedColor.toString())
            }

            Text { text: "Dynamic"; color: theme.muted; font.pixelSize: 13 }
                Switch {
                    checked: backend.dynamicMode
                    onToggled: backend.setDynamicMode(checked)
                }

                // App preferences. Only the tray lives here so far; it is the
                // one setting that changes what closing the window means.
                Rectangle {
                    Layout.preferredHeight: 26
                    Layout.preferredWidth: 26
                    radius: theme.radius
                    color: prefsHover.hovered ? theme.cell : theme.panel2
                    border.color: theme.line
                    Behavior on color { ColorAnimation { duration: 120 } }
                    Text {
                        anchors.centerIn: parent
                        text: "⚙"; color: theme.muted; font.pixelSize: 14
                    }
                    HoverHandler { id: prefsHover; cursorShape: Qt.PointingHandCursor }
                    TapHandler { onTapped: prefsPopup.open() }
                    ToolTip.visible: prefsHover.hovered
                    ToolTip.text: "App preferences"

                    Popup {
                        id: prefsPopup
                        objectName: "prefsPopup"
                        x: parent.width - width
                        y: parent.height + 6
                        width: 290
                        modal: false
                        focus: true
                        background: Rectangle {
                            radius: theme.radius; color: theme.panel
                            border.color: theme.line
                        }
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 8

                            Text {
                                text: "Preferences"; color: theme.text
                                font.pixelSize: 13; font.bold: true
                            }

                            // Brightness lived in the top bar until the bar ran
                            // out of room. The device quantises to steps of 10,
                            // so the slider is stepped to match rather than
                            // pretending to be continuous.
                            RowLayout {
                                Layout.fillWidth: true; spacing: 6
                                Text {
                                    text: "Brightness"; color: theme.muted
                                    font.pixelSize: 11
                                }
                                Slider {
                                    id: brightnessSlider
                                    Layout.fillWidth: true
                                    from: 0; to: 100; stepSize: 10
                                    snapMode: Slider.SnapAlways
                                    value: backend.brightness
                                    onMoved: backend.setBrightness(value)
                                }
                                Text {
                                    text: Math.round(brightnessSlider.value) + "%"
                                    color: theme.muted; font.pixelSize: 11
                                    Layout.preferredWidth: 34
                                    horizontalAlignment: Text.AlignRight
                                }
                            }

                            Rectangle { Layout.fillWidth: true; height: 1; color: theme.line }

                            RowLayout {
                                Layout.fillWidth: true; spacing: 6
                                Text {
                                    Layout.fillWidth: true
                                    text: "System tray"; color: theme.muted; font.pixelSize: 11
                                }
                                Switch {
                                    enabled: backend.traySupported
                                    checked: backend.trayEnabled
                                    onToggled: backend.setTrayEnabled(checked)
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                visible: !backend.traySupported
                                text: "This desktop has no system tray for the app to sit in."
                                color: theme.warn; font.pixelSize: 10; wrapMode: Text.WordWrap
                            }

                            RowLayout {
                                Layout.fillWidth: true; spacing: 6
                                Text {
                                    Layout.fillWidth: true
                                    text: "Close to tray"; color: theme.muted; font.pixelSize: 11
                                }
                                Switch {
                                    enabled: backend.trayEnabled
                                    checked: backend.closeToTray
                                    onToggled: backend.setCloseToTray(checked)
                                }
                            }

                            RowLayout {
                                Layout.fillWidth: true; spacing: 6
                                Text {
                                    Layout.fillWidth: true
                                    text: "Start hidden"; color: theme.muted; font.pixelSize: 11
                                }
                                Switch {
                                    enabled: backend.trayEnabled
                                    checked: backend.startHidden
                                    onToggled: backend.setStartHidden(checked)
                                }
                            }

                            Text {
                                Layout.fillWidth: true
                                text: backend.closeToTray
                                      ? "Closing the window leaves the app running in the tray. "
                                        + "Quit from the tray menu."
                                      : "Closing the window quits the app."
                                color: theme.muted; font.pixelSize: 10; wrapMode: Text.WordWrap
                            }
                        }
                    }
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
                TextField {
                    id: librarySearch
                    objectName: "librarySearch"   // lets UI checks drive it
                    Layout.fillWidth: true
                    placeholderText: "Search actions…"
                    color: theme.text
                    placeholderTextColor: theme.muted
                    font.pixelSize: 13
                    leftPadding: 10
                    background: Rectangle {
                        radius: theme.radius; color: theme.panel2
                        border.color: librarySearch.activeFocus ? theme.accent : theme.line
                    }
                    Keys.onEscapePressed: text = ""
                }
                Text {
                    Layout.fillWidth: true
                    text: librarySearch.text === ""
                          ? "Drag an action onto a control"
                          : libList.count + (libList.count === 1 ? " match" : " matches")
                            + " · Esc to clear"
                    color: theme.muted; font.pixelSize: 11
                }
                ListView {
                    id: libList
                    Layout.fillWidth: true; Layout.fillHeight: true; clip: true; spacing: 4
                    model: backend.filterLibrary(librarySearch.text)
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
            id: rightPanel
            Layout.preferredWidth: 300; Layout.fillHeight: true
            radius: theme.radius; color: theme.panel; border.color: theme.line
            // Without this the column lays out at its natural height and draws
            // straight over the window edge when the window is made smaller.
            clip: true

            // Profiles is a big fixed block; with a control selected it leaves
            // the inspector a sliver. Collapse it when the user starts editing
            // a control, expand again when they clear the selection.
            property bool profilesCollapsed: false
            Connections {
                target: backend
                function onSelectionChanged() {
                    rightPanel.profilesCollapsed = backend.selectedControl !== ""
                }
            }

            ColumnLayout {
                anchors.fill: parent; anchors.margins: 12; spacing: 10

                RowLayout {
                    Layout.fillWidth: true
                    Text {
                        text: "Profiles"; color: theme.text
                        font.pixelSize: 15; font.bold: true
                        Layout.fillWidth: true
                    }
                    Text {
                        text: rightPanel.profilesCollapsed
                              ? backend.activeProfile + "  ▸" : "▾"
                        color: theme.muted; font.pixelSize: 12
                    }
                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                    TapHandler {
                        onTapped: rightPanel.profilesCollapsed = !rightPanel.profilesCollapsed
                    }
                }

                ListView {
                    visible: !rightPanel.profilesCollapsed
                    Layout.fillWidth: true; Layout.preferredHeight: 150; clip: true; spacing: 4
                    model: backend.profiles
                    delegate: Rectangle {
                        width: ListView.view.width; height: 36; radius: theme.radius
                        color: modelData === backend.activeProfile ? theme.accent
                               : (hover.hovered ? theme.cell : theme.panel2)
                        opacity: modelData === backend.activeProfile ? 0.9 : 1.0
                        Behavior on color { ColorAnimation { duration: 120 } }
                        HoverHandler { id: hover; cursorShape: Qt.PointingHandCursor }
                        TapHandler {
                            onTapped: root.withDraftCheck(function() {
                                backend.loadProfile(modelData)
                            })
                        }
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
                    visible: !rightPanel.profilesCollapsed
                    Layout.fillWidth: true
                    spacing: 6
                    ActionButton {
                        label: "New"
                        onClicked: root.withDraftCheck(function() {
                            nameDialog.mode = "create"; nameDialog.open()
                        })
                    }
                    ActionButton {
                        label: "Duplicate"
                        enabledFlag: backend.activeProfile !== "(none)"
                        onClicked: root.withDraftCheck(function() {
                            nameDialog.mode = "duplicate"
                            nameDialog.source = backend.activeProfile
                            nameDialog.open()
                        })
                    }
                    ActionButton {
                        label: "Rename"
                        enabledFlag: backend.activeProfile !== "(none)"
                        onClicked: root.withDraftCheck(function() {
                            nameDialog.mode = "rename"
                            nameDialog.source = backend.activeProfile
                            nameDialog.open()
                        })
                    }
                    ActionButton {
                        label: "Import"
                        onClicked: root.withDraftCheck(function() { importDialog.open() })
                    }
                    ActionButton {
                        label: "Export"
                        enabledFlag: backend.activeProfile !== "(none)"
                        onClicked: exportDialog.open()
                    }
                    ActionButton {
                        label: "Delete"
                        // never the last one (nothing would be left to load), and
                        // never a profile that ships with the app
                        enabledFlag: backend.activeProfile !== "(none)"
                                     && backend.profiles.length > 1
                                     && backend.activeProfileIsUser
                        onClicked: {
                            deleteDialog.target = backend.activeProfile
                            deleteDialog.open()
                        }
                    }
                }

                // -------- Dynamic mode: focused app -> profile --------
                Rectangle {
                    visible: !rightPanel.profilesCollapsed
                    Layout.fillWidth: true; height: 1; color: theme.line
                }
                ColumnLayout {
                    visible: !rightPanel.profilesCollapsed
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
                                             && typeBox.currentText !== "macro"
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
                                // ---- macro editor ----
                                // One step per line. A list editor would need a
                                // schema change and a lot of UI; text keeps the
                                // value a plain string and stays editable.
                                ColumnLayout {
                                    visible: typeBox.currentText === "macro"
                                    Layout.fillWidth: true; spacing: 4

                                    // Two views of the same value: a list of
                                    // steps, and the raw text. The text is what
                                    // is stored, so neither view is primary.
                                    RowLayout {
                                        Layout.fillWidth: true; spacing: 6
                                        Text {
                                            text: "Steps"; color: theme.muted
                                            font.pixelSize: 11; Layout.fillWidth: true
                                        }
                                        ActionButton {
                                            label: macroList.showText ? "List view" : "Text view"
                                            onClicked: {
                                                // Moving between views must not
                                                // lose an unapplied edit.
                                                if (!macroList.showText)
                                                    macroField.text = modelData.value
                                                macroList.showText = !macroList.showText
                                            }
                                        }
                                    }

                                    ColumnLayout {
                                        id: macroList
                                        property bool showText: false
                                        visible: !showText
                                        Layout.fillWidth: true
                                        spacing: 3

                                        function steps() { return backend.macroSteps(modelData.value) }

                                        function commit(list) {
                                            backend.setActionSlot(modelData.slot, "macro",
                                                                  backend.macroText(list))
                                        }

                                        Repeater {
                                            model: backend.macroSteps(modelData.value)
                                            delegate: RowLayout {
                                                required property var modelData
                                                required property int index
                                                Layout.fillWidth: true; spacing: 4

                                                ComboBox {
                                                    Layout.preferredWidth: 92
                                                    model: backend.macroStepKinds
                                                    currentIndex: backend.macroStepKinds.indexOf(parent.modelData.kind)
                                                    onActivated: {
                                                        var list = macroList.steps()
                                                        list[parent.index].kind = currentText
                                                        macroList.commit(list)
                                                    }
                                                }
                                                TextField {
                                                    Layout.fillWidth: true
                                                    text: parent.modelData.value
                                                    color: theme.text
                                                    font.pixelSize: 11
                                                    background: Rectangle {
                                                        radius: 5; color: theme.panel2
                                                        border.color: theme.line
                                                    }
                                                    onEditingFinished: {
                                                        var list = macroList.steps()
                                                        list[parent.index].value = text
                                                        macroList.commit(list)
                                                    }
                                                }
                                                Text {
                                                    text: "↑"; color: theme.muted; font.pixelSize: 12
                                                    visible: parent.index > 0
                                                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                                                    TapHandler {
                                                        onTapped: {
                                                            var list = macroList.steps()
                                                            var i = parent.index
                                                            var t = list[i - 1]
                                                            list[i - 1] = list[i]; list[i] = t
                                                            macroList.commit(list)
                                                        }
                                                    }
                                                }
                                                Text {
                                                    text: "✕"; color: theme.muted; font.pixelSize: 12
                                                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                                                    TapHandler {
                                                        onTapped: {
                                                            var list = macroList.steps()
                                                            list.splice(parent.index, 1)
                                                            macroList.commit(list)
                                                        }
                                                    }
                                                }
                                            }
                                        }

                                        Text {
                                            visible: backend.macroSteps(modelData.value).length === 0
                                            text: "No steps yet."
                                            color: theme.muted; font.pixelSize: 10
                                        }

                                        ActionButton {
                                            label: "+ Add step"
                                            onClicked: {
                                                var list = macroList.steps()
                                                list.push({kind: "hotkey", value: "ctrl+c"})
                                                macroList.commit(list)
                                            }
                                        }
                                    }

                                    ScrollView {
                                        visible: macroList.showText
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 110
                                        clip: true
                                        TextArea {
                                            id: macroField
                                            text: modelData.value
                                            color: theme.text
                                            font.family: "monospace"
                                            font.pixelSize: 12
                                            wrapMode: TextArea.NoWrap
                                            placeholderText: "hotkey ctrl+c\nwait 200\nhotkey ctrl+v"
                                            placeholderTextColor: theme.muted
                                            background: Rectangle {
                                                radius: 6; color: theme.panel2
                                                border.color: macroField.activeFocus
                                                              ? theme.accent : theme.line
                                            }
                                            onEditingFinished: backend.setActionSlot(
                                                modelData.slot, "macro", text)
                                        }
                                    }

                                    RowLayout {
                                        visible: macroList.showText
                                        Layout.fillWidth: true
                                        Text {
                                            Layout.fillWidth: true
                                            text: backend.describeMacro(macroField.text)
                                            color: backend.macroProblems(macroField.text).length > 0
                                                   ? theme.warn : theme.muted
                                            font.pixelSize: 10
                                        }
                                        ActionButton {
                                            label: "Apply"
                                            onClicked: backend.setActionSlot(
                                                modelData.slot, "macro", macroField.text)
                                        }
                                    }

                                    Repeater {
                                        model: macroList.showText
                                               ? backend.macroProblems(macroField.text) : []
                                        delegate: Text {
                                            required property string modelData
                                            Layout.fillWidth: true
                                            text: modelData; color: theme.warn
                                            font.pixelSize: 10; wrapMode: Text.WordWrap
                                        }
                                    }

                                    Text {
                                        Layout.fillWidth: true
                                        visible: macroList.showText
                                        text: "Steps: hotkey · text · wait <ms> · scroll <dir> [n] "
                                              + "· media · keyboard · command"
                                        color: theme.muted; font.pixelSize: 10
                                        wrapMode: Text.WordWrap
                                    }
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

                                // ---- secondary (fn) binding ----
                                // Collapsed unless it has one, so the common
                                // case stays a single editor per slot.
                                RowLayout {
                                    Layout.fillWidth: true; spacing: 6
                                    Text {
                                        text: "fn"; color: theme.warn
                                        font.pixelSize: 10; font.bold: true
                                    }
                                    ComboBox {
                                        id: fnTypeBox
                                        Layout.fillWidth: true
                                        model: backend.selectedActionTypes
                                        currentIndex: Math.max(0,
                                            backend.selectedActionTypes.indexOf(modelData.fnType))
                                        onActivated: backend.setFnActionSlot(
                                            modelData.slot, currentText, fnValueField.text)
                                    }
                                }
                                ComboBox {
                                    visible: !!backend.valueOptions[fnTypeBox.currentText]
                                    Layout.fillWidth: true
                                    textRole: "label"
                                    model: backend.valueOptions[fnTypeBox.currentText] || []
                                    currentIndex: {
                                        var opts = backend.valueOptions[fnTypeBox.currentText] || []
                                        for (var i = 0; i < opts.length; i++)
                                            if (opts[i].value === modelData.fnValue)
                                                return i
                                        return 0
                                    }
                                    onActivated: {
                                        var opts = backend.valueOptions[fnTypeBox.currentText] || []
                                        if (opts[currentIndex])
                                            backend.setFnActionSlot(modelData.slot,
                                                fnTypeBox.currentText, opts[currentIndex].value)
                                    }
                                }
                                TextField {
                                    id: fnValueField
                                    Layout.fillWidth: true
                                    visible: fnTypeBox.currentText !== "none"
                                             && fnTypeBox.currentText !== "back"
                                             && !backend.valueOptions[fnTypeBox.currentText]
                                    text: modelData.fnValue
                                    color: theme.text
                                    placeholderText: "secondary, used while fn is held"
                                    placeholderTextColor: theme.muted
                                    background: Rectangle {
                                        radius: 6; color: theme.panel2
                                        border.color: fnValueField.activeFocus ? theme.warn : theme.line
                                    }
                                    onEditingFinished: backend.setFnActionSlot(
                                        modelData.slot, fnTypeBox.currentText, text)
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

                        // Workspace name (the eight round keys). Same field as
                        // the header chip, reachable from wherever you are.
                        ColumnLayout {
                            visible: backend.selectedIsWorkspace
                            Layout.fillWidth: true; spacing: 6
                            Rectangle { Layout.fillWidth: true; height: 1; color: theme.line }
                            Text { text: "Workspace name"; color: theme.muted; font.pixelSize: 12 }
                            TextField {
                                id: wsInspectorName
                                objectName: "wsInspectorName"   // lets UI checks drive it
                                Layout.fillWidth: true
                                text: backend.workspaceNameOf(backend.selectedControl)
                                placeholderText: "Unnamed"
                                color: theme.text
                                placeholderTextColor: theme.muted
                                font.pixelSize: 13
                                leftPadding: 8
                                background: Rectangle {
                                    radius: theme.radius; color: theme.panel2
                                    border.color: wsInspectorName.activeFocus ? theme.accent : theme.line
                                }
                                onEditingFinished:
                                    backend.setWorkspaceName(backend.selectedControl, text)
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
