import QtQuick
import QtQuick.Layouts
import QtQuick.Effects

// CT-accurate device mock that MIRRORS the loaded profile and lets you SELECT a
// control (tap it) to edit in the right-hand inspector. Images come from
// backend.keyImages; bound controls light up from backend.boundActions; the
// selected control gets an 'ok'-coloured ring.
Item {
    id: dv
    property var theme
    property int cols: backend.columns
    property int rows: backend.rows

    readonly property int keySize: 74
    readonly property int gap: 8

    // How loudly the editor draws over the device. Selection is the thing you
    // are working on and should be obvious; "something is bound here" is true
    // of most of a finished deck, and at full strength it turned the mirror
    // back into a wiring diagram.
    readonly property real boundGlow: 0.28
    readonly property real selectedGlow: 0.95

    implicitWidth: body.width
    implicitHeight: body.height

    // ---- profile lookups (recompute on backend.stateChanged) -------------
    function img(key) { return backend.keyImages[key] || "" }
    function bound(key) { return backend.boundActions[key] !== undefined }
    function encBound(base) {
        var b = backend.boundActions
        return b[base] !== undefined || b[base + "-l"] !== undefined || b[base + "-r"] !== undefined
    }
    function isSel(key) { return key !== "" && backend.selectedControl === key }
    function label(key) { return backend.controlLabels[key] }
    function led(key) { return backend.controlLeds[key] || "" }
    function bg(key) { return backend.controlBgs[key] || "" }
    // approximate the device's shrink-mode label band height for the mirror
    function shrinkBand(h) { return Math.round(h * 0.3) }

    // text-label overlay for image-bearing controls (mirrors the device:
    // over = text over the image; bar = text on a band; shrink = band at an edge
    // with the image resized beside it; the image inset is done by each cell)
    component CtrlLabel: Item {
        id: cl
        property var lbl: undefined
        anchors.fill: parent
        visible: lbl !== undefined && lbl !== null
        readonly property string lmode: lbl ? (lbl.mode || "over") : "over"
        readonly property string lpos: lbl ? (lbl.pos || "bottom") : "bottom"
        readonly property int pad: 2
        // one text position for every mode so shrink clears the edge like bar does
        readonly property real textY: lpos === "top" ? 6
            : lpos === "middle" ? (height - lt.implicitHeight) / 2
            : height - lt.implicitHeight - 10
        Rectangle {   // band behind the text (bar + shrink modes)
            visible: cl.lmode === "bar" || cl.lmode === "shrink"
            width: parent.width
            color: (cl.lbl && cl.lbl.bar_color) ? cl.lbl.bar_color : Qt.rgba(0, 0, 0, 0.82)
            // bar: wrap the text; shrink: run from the text to the near edge
            y: (cl.lmode === "shrink" && cl.lpos === "top") ? 0 : (cl.textY - cl.pad)
            height: cl.lmode !== "shrink" ? (lt.implicitHeight + 2 * cl.pad)
                  : (cl.lpos === "top" ? (cl.textY + lt.implicitHeight + cl.pad)
                                       : (cl.height - (cl.textY - cl.pad)))
        }
        Text {
            id: lt
            text: cl.lbl ? (cl.lbl.text || "") : ""
            color: "white"; font.pixelSize: 11; font.bold: true
            width: parent.width; horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight; maximumLineCount: 1
            style: Text.Outline; styleColor: "black"
            y: cl.textY
        }
    }

    // ---- surfaces --------------------------------------------------------
    // The device is a dark slab lit from above. Everything below leans on that
    // one fact: a raised thing is bright along its top edge and dark along its
    // bottom, a recessed thing is the other way round, and nothing is a flat
    // fill. Done with layered rectangles rather than images so it costs no
    // assets and works at any size.

    // The lit top edge of a round thing, which is a crescent and not a line.
    // A straight hairline across the top of a circle's bounding box sits
    // outside the circle everywhere except its centre point, so it floated
    // above every key as a stray bar. This draws the whole outline and clips
    // it to the top half, which is where light from above actually lands.
    component RimLight: Item {
        id: rim
        property real strength: 0.09
        anchors.fill: parent

        // Two arcs, not one. A single crescent clipped at the halfway line
        // ends abruptly at nine and three o'clock; a shorter, brighter cap over
        // a longer, dimmer one puts the falloff where a highlight has one.
        Repeater {
            model: [{reach: 0.5, weight: 0.6}, {reach: 0.26, weight: 1.0}]
            Item {
                required property var modelData
                width: rim.width
                height: rim.height * modelData.reach
                clip: true
                Rectangle {
                    width: rim.width
                    height: rim.height
                    radius: height / 2
                    color: "transparent"
                    border.color: "#ffffff"
                    border.width: 1
                    opacity: rim.strength * parent.modelData.weight
                }
            }
        }
    }

    // The dark well a key or a screen sits in.
    component Recess: Rectangle {
        property real round: 8
        anchors.fill: parent
        radius: round
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#050507" }
            GradientStop { position: 1.0; color: "#0d0d12" }
        }
        border.color: "#000000"; border.width: 1
    }

    // Glass over a screen: a soft diagonal sheen, strongest at the top left.
    component Glass: Rectangle {
        property real round: 6
        anchors.fill: parent
        radius: round
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#ffffff" }
            GradientStop { position: 0.42; color: "#00ffffff" }
            GradientStop { position: 1.0; color: "#00ffffff" }
        }
        opacity: 0.05
    }

    // The ridges around an encoder or the wheel. Cheap knurling: thin bars laid
    // round the rim, alternating light and dark so the edge reads as machined
    // rather than drawn.
    component Knurl: Item {
        id: knurl
        property int teeth: 28
        property real inset: 3
        property real len: 5
        anchors.fill: parent
        Repeater {
            model: knurl.teeth
            Rectangle {
                required property int index
                width: 1.1
                height: knurl.len
                radius: 0.55
                color: index % 2 ? "#ffffff" : "#000000"
                opacity: index % 2 ? 0.16 : 0.30
                x: knurl.width / 2 - width / 2
                y: knurl.inset
                // Each bar is rotated about the centre of the knob, which is
                // this far below its own top edge.
                transform: Rotation {
                    origin.x: 0.55
                    origin.y: knurl.height / 2 - knurl.inset
                    angle: index * 360 / knurl.teeth
                }
            }
        }
    }

    // reusable pieces ------------------------------------------------------
    component Encoder: Rectangle {
        id: enc
        property bool active: false
        property string ctlKey: ""
        property bool sel: dv.isSel(ctlKey)
        width: 54; height: 54; radius: 27
        // The body of the knob: dark anodised metal, lit from above.
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#3a3a44" }
            GradientStop { position: 0.5; color: "#23232b" }
            GradientStop { position: 1.0; color: "#141419" }
        }
        border.color: encDrop.containsDrag ? theme.accent
                    : (sel ? theme.ok : (active ? theme.accent : "#0a0a0e"))
        border.width: encDrop.containsDrag ? 4 : 1

        Knurl { teeth: 44; inset: 2; len: 7; visible: !encDrop.containsDrag }

        // The flat top face, inset from the knurled rim.
        Rectangle {
            anchors.centerIn: parent
            width: parent.width - 16; height: width; radius: width / 2
            gradient: Gradient {
                GradientStop { position: 0.0; color: "#2a2a33" }
                GradientStop { position: 1.0; color: "#17171d" }
            }
            border.color: "#0c0c11"; border.width: 1
            RimLight { strength: 0.10 }
        }

        // A ring of colour when the knob is bound or selected: the state has
        // to survive the knob no longer being a flat block of accent colour.
        Rectangle {
            anchors.centerIn: parent
            width: parent.width - 6; height: width; radius: width / 2
            color: "transparent"
            visible: sel || active
            border.width: sel ? 2 : 1
            border.color: sel ? theme.ok : theme.accent
            opacity: sel ? dv.selectedGlow : dv.boundGlow
            Behavior on opacity { NumberAnimation { duration: 130 } }
        }

        Rectangle {  // knob indicator notch (hidden while choosing a drop slot)
            visible: !encDrop.containsDrag
            width: 3; height: 10; radius: 1.5
            color: (active || sel) ? theme.text : "#8a8a96"
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top; anchors.topMargin: 11
        }
        TapHandler { enabled: ctlKey !== ""; onTapped: backend.selectControl(ctlKey) }
        // one drop target; the vertical third under the cursor picks the slot
        // (top = rotate ◀, middle = press, bottom = rotate ▶)
        DropArea {
            id: encDrop; anchors.fill: parent
            property int zone: 1
            onPositionChanged: (drag) => { var t = height / 3
                zone = drag.y < t ? 0 : (drag.y < 2 * t ? 1 : 2) }
            onDropped: (drop) => {
                if (enc.ctlKey === "" || !drop.source) return
                var t = height / 3
                var z = drop.y < t ? 0 : (drop.y < 2 * t ? 1 : 2)
                var slot = z === 0 ? enc.ctlKey + "-l" : z === 2 ? enc.ctlKey + "-r" : enc.ctlKey
                backend.applyLibraryAction(slot, drop.source.aType, drop.source.aValue, drop.source.aLabel)
            }
        }
        Column {   // drop-slot guide, shown while a drag hovers the knob
            anchors.centerIn: parent; visible: encDrop.containsDrag; z: 5; spacing: 0
            Repeater {
                model: [{t: "◀", z: 0}, {t: "Press", z: 1}, {t: "▶", z: 2}]
                Rectangle {
                    width: enc.width; height: enc.height / 3
                    color: encDrop.zone === modelData.z ? theme.accent : Qt.rgba(0, 0, 0, 0.62)
                    Text { anchors.centerIn: parent; text: modelData.t
                        color: "white"; font.pixelSize: 9; font.bold: true }
                }
            }
        }
        scale: encDrop.containsDrag ? 1.14 : 1.0
        Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        Behavior on color { ColorAnimation { duration: 130 } }
        Behavior on border.color { ColorAnimation { duration: 130 } }
    }

    component RoundBtn: Rectangle {
        id: rb
        property string label: ""
        property bool active: false
        // Workspace keys switch as well as select, the way pressing the key on
        // the device does; every other button only selects.
        property bool switchesWorkspace: false
        // "This is the workspace on the device" is worth shouting about.
        // "This key has something bound to it" is true of most of a finished
        // deck and only has to be legible.
        property bool strongActive: false
        property color activeColor: theme.accent
        property string ctlKey: ""
        property string ledColor: ""
        property bool sel: dv.isSel(ctlKey)
        width: 40; height: 40; radius: 20
        // A rubber key sunk into the body: dark ring, domed face, and whatever
        // the LED under it is doing.
        color: "#0b0b0f"
        // The seat the key sits in is always dark. State is the two rings
        // inside; a coloured seat as well was a third ring saying the same
        // thing louder.
        border.color: rbDrop.containsDrag ? theme.accent : "#000000"
        border.width: rbDrop.containsDrag ? 3 : 1

        Rectangle {          // the dome
            anchors.centerIn: parent
            width: parent.width - 6; height: width; radius: width / 2
            gradient: Gradient {
                GradientStop { position: 0.0
                    color: rb.ledColor !== "" ? Qt.lighter(rb.ledColor, 1.5) : "#33333d" }
                GradientStop { position: 0.55
                    color: rb.ledColor !== "" ? rb.ledColor : "#1e1e25" }
                GradientStop { position: 1.0
                    color: rb.ledColor !== "" ? Qt.darker(rb.ledColor, 1.6) : "#121217" }
            }
            border.color: "#08080b"; border.width: 1
            RimLight { strength: rb.ledColor !== "" ? 0.22 : 0.10 }
            // Two different things, drawn differently. Selection and the live
            // workspace glow past the key's edge, the way a lit one does
            // through the rubber. "Something is bound here" is a rim inside
            // the key: legible up close, and it does not halo a cluster of
            // buttons into a blue constellation.
            Rectangle {
                anchors.centerIn: parent
                width: parent.width + 6; height: width; radius: width / 2
                color: "transparent"
                visible: rb.sel || (rb.active && rb.strongActive)
                border.width: 2
                border.color: rb.sel ? theme.ok : rb.activeColor
                opacity: rb.sel ? dv.selectedGlow : 0.8
                Behavior on opacity { NumberAnimation { duration: 130 } }
            }
            Rectangle {
                anchors.centerIn: parent
                width: parent.width - 3; height: width; radius: width / 2
                color: "transparent"
                visible: rb.active && !rb.strongActive && !rb.sel
                border.width: 1
                border.color: rb.activeColor
                opacity: dv.boundGlow
            }
        }
        Text { anchors.centerIn: parent; text: label
            color: (active || sel || ledColor !== "") ? theme.text : "#9a9aa6"
            font.pixelSize: 11
            style: Text.Outline; styleColor: "#00000060" }
        TapHandler {
            enabled: rb.ctlKey !== ""
            onTapped: rb.switchesWorkspace ? backend.showWorkspace(rb.ctlKey)
                                           : backend.selectControl(rb.ctlKey)
        }
        DropArea {
            id: rbDrop; anchors.fill: parent
            onDropped: (drop) => { if (ctlKey !== "" && drop.source)
                backend.applyLibraryAction(ctlKey, drop.source.aType, drop.source.aValue, drop.source.aLabel) }
        }
        scale: rbDrop.containsDrag ? 1.12 : 1.0
        Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        Behavior on color { ColorAnimation { duration: 130 } }
        Behavior on border.color { ColorAnimation { duration: 130 } }
    }

    component SideCell: Rectangle {
        property string ctlKey: ""
        // "single" layout: one image for the whole strip, so the cell is as
        // tall as the three it replaces, gaps included.
        property bool tall: false
        property bool sel: dv.isSel(ctlKey)
        width: 30
        height: tall ? dv.keySize * 3 + dv.gap * 2 : dv.keySize
        radius: 6
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#20202a" }
            GradientStop { position: 1.0; color: "#14141b" }
        }
        border.color: "#000000"
        border.width: 1
        clip: true
        Rectangle {   // background fill colour (behind the image)
            anchors.fill: parent; anchors.margins: 1; radius: 5
            visible: dv.bg(ctlKey) !== ""; color: dv.bg(ctlKey) !== "" ? dv.bg(ctlKey) : "transparent"
        }
        Image {
            property var _l: dv.label(ctlKey)
            property bool _shrink: _l ? _l.mode === "shrink" : false
            property bool _top: _l ? _l.pos === "top" : false
            property int _band: _shrink ? dv.shrinkBand(parent.height) : 0
            source: dv.img(ctlKey); visible: source != ""
            fillMode: Image.PreserveAspectFit; asynchronous: true
            anchors.fill: parent; anchors.leftMargin: 1; anchors.rightMargin: 1
            anchors.topMargin: (_shrink && _top) ? _band : 1
            anchors.bottomMargin: (_shrink && !_top) ? _band : 1
        }
        CtrlLabel { lbl: dv.label(ctlKey) }
        // The state ring, over the content rather than instead of it, so a
        // bound cell keeps its image at full strength.
        Rectangle {
            anchors.fill: parent; anchors.margins: 1; radius: 5
            color: "transparent"
            border.color: scDrop.containsDrag ? theme.accent
                        : (sel ? theme.ok : theme.accent)
            border.width: (sel || scDrop.containsDrag) ? 2 : 1
            visible: sel || scDrop.containsDrag || dv.bound(ctlKey)
            opacity: (sel || scDrop.containsDrag) ? dv.selectedGlow : dv.boundGlow
            Behavior on opacity { NumberAnimation { duration: 130 } }
        }
        TapHandler { onTapped: backend.selectControl(ctlKey) }
        DropArea {
            id: scDrop; anchors.fill: parent
            onDropped: (drop) => { if (drop.source)
                backend.applyLibraryAction(ctlKey, drop.source.aType, drop.source.aValue, drop.source.aLabel) }
        }
        Behavior on border.color { ColorAnimation { duration: 130 } }
    }

    // A shadow under the slab. Stacked translucent rounded rectangles rather
    // than a blur effect: the device is nearly the same value as the panel
    // behind it, and without something to separate them it reads as a diagram
    // printed on the background.
    Repeater {
        model: 5
        Rectangle {
            required property int index
            anchors.centerIn: body
            width: body.width + index * 5
            height: body.height + index * 5
            radius: body.radius + index * 2
            color: "#000000"
            opacity: 0.10 - index * 0.017
            z: -1
        }
    }

    Rectangle {
        id: body
        width: stack.implicitWidth + 48
        height: stack.implicitHeight + 80
        radius: 22
        // The chassis: a dark slab lit from above, with a machined edge.
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#26262e" }
            GradientStop { position: 0.06; color: "#17171d" }
            GradientStop { position: 0.85; color: "#101015" }
            GradientStop { position: 1.0; color: "#08080b" }
        }
        border.color: "#000000"; border.width: 1

        // The bright hairline along the top edge is what makes it read as a
        // solid object rather than a dark rectangle.
        Rectangle {
            anchors.top: parent.top; anchors.topMargin: 1
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width - 2 * parent.radius; height: 1
            color: "#ffffff"; opacity: 0.10
        }
        Rectangle {
            anchors.bottom: parent.bottom; anchors.bottomMargin: 1
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width - 2 * parent.radius; height: 1
            color: "#000000"; opacity: 0.5
        }

        // submenu breadcrumb badge
        Rectangle {
            visible: backend.menuDepth > 0
            anchors.top: parent.top; anchors.left: parent.left
            anchors.margins: 12
            width: bc.width + 20; height: 24; radius: 12
            color: bcHover.hovered ? theme.cell : theme.panel2; border.color: theme.accent
            Behavior on color { ColorAnimation { duration: 120 } }
            Text { id: bc; anchors.centerIn: parent
                text: "← submenu " + backend.menuDepth
                color: theme.accent; font.pixelSize: 11; font.bold: true }
            HoverHandler { id: bcHover; cursorShape: Qt.PointingHandCursor }
            TapHandler { onTapped: backend.goBack() }
        }

        ColumnLayout {
            id: stack
            anchors.centerIn: parent
            spacing: 26

            // ---- top zone: encoders | strip | grid | strip | encoders ----
            RowLayout {
                id: topZone
                spacing: 14
                // Encoders and side strips come from the backend rather than
                // being written out, so a Live S renders with two dials and no
                // side screens instead of the CT's six and two.
                ColumnLayout {
                    spacing: 20
                    visible: backend.encodersLeft.length > 0
                    Repeater {
                        model: backend.encodersLeft
                        Encoder { ctlKey: modelData; active: dv.encBound(modelData) }
                    }
                }

                // left side strip: three cells, or one tall image
                ColumnLayout {
                    spacing: dv.gap
                    visible: backend.sideCellsLeft.length > 0
                    Repeater {
                        model: backend.sideLayout["L"] === "single"
                               ? backend.sideCellsLeft.slice(0, 1)
                               : backend.sideCellsLeft
                        SideCell {
                            ctlKey: modelData
                            tall: backend.sideLayout["L"] === "single"
                        }
                    }
                }

                // center touch-key grid
                // One screen behind the keys, not twelve separate ones: that
                // is what the hardware is, and the shared glass is what makes
                // the grid read as a display.
                Rectangle {
                    radius: 8; color: "#07070a"
                    Layout.preferredWidth: grid.width + 12
                    Layout.preferredHeight: grid.height + 12
                    Recess { round: 8 }
                    GridLayout {
                        id: grid
                        anchors.centerIn: parent
                        columns: dv.cols; rowSpacing: dv.gap; columnSpacing: dv.gap
                        Repeater {
                            model: dv.cols * dv.rows
                            Rectangle {
                                property int r: Math.floor(index / dv.cols) + 1
                                property int c: index % dv.cols + 1
                                property string key: "tb" + r + c
                                property string src: dv.img(key)
                                property bool sel: dv.isSel(key)
                                width: dv.keySize; height: dv.keySize; radius: 8
                                clip: true
                                // A tile of the screen rather than a button:
                                // near-black, lifted a touch at the top.
                                gradient: Gradient {
                                    GradientStop { position: 0.0; color: "#20202a" }
                                    GradientStop { position: 1.0; color: "#14141b" }
                                }
                                Rectangle {   // background fill colour (behind the image)
                                    anchors.fill: parent; anchors.margins: 1; radius: 7
                                    visible: dv.bg(parent.key) !== ""
                                    color: dv.bg(parent.key) !== "" ? dv.bg(parent.key) : "transparent"
                                }
                                Image {
                                    property var _l: dv.label(parent.key)
                                    property bool _shrink: _l ? _l.mode === "shrink" : false
                                    property bool _top: _l ? _l.pos === "top" : false
                                    property int _band: _shrink ? dv.shrinkBand(dv.keySize) : 0
                                    source: parent.src; visible: source != ""
                                    fillMode: Image.PreserveAspectFit; asynchronous: true
                                    anchors.fill: parent; anchors.leftMargin: 1; anchors.rightMargin: 1
                                    anchors.topMargin: (_shrink && _top) ? _band : 1
                                    anchors.bottomMargin: (_shrink && !_top) ? _band : 1
                                }
                                CtrlLabel { lbl: dv.label(parent.key) }
                                Rectangle {  // outline
                                    anchors.fill: parent; anchors.margins: 1; radius: 7
                                    color: "transparent"
                                    border.color: tbDrop.containsDrag ? theme.accent
                                                : (parent.sel ? theme.ok
                                                : (dv.bound(parent.key) ? theme.accent : "#000000"))
                                    border.width: (parent.sel || tbDrop.containsDrag) ? 2 : 1
                                    // A bound key already shows its own image
                                    // and label; the ring only has to hint.
                                    opacity: (parent.sel || tbDrop.containsDrag)
                                             ? dv.selectedGlow
                                             : (dv.bound(parent.key) ? dv.boundGlow : 0.6)
                                    Behavior on border.color { ColorAnimation { duration: 130 } }
                                    Behavior on opacity { NumberAnimation { duration: 130 } }
                                }
                                Rectangle {  // bound-but-no-image dot
                                    visible: parent.src == "" && dv.bound(parent.key)
                                    anchors.centerIn: parent
                                    width: 8; height: 8; radius: 4; color: theme.accent
                                }
                                TapHandler { onTapped: backend.selectControl(parent.key) }
                                DropArea {
                                    id: tbDrop; anchors.fill: parent
                                    onDropped: (drop) => { if (drop.source)
                                        backend.applyLibraryAction(parent.key, drop.source.aType, drop.source.aValue, drop.source.aLabel) }
                                }
                                scale: tbDrop.containsDrag ? 1.06 : 1.0
                                Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
                                Behavior on color { ColorAnimation { duration: 130 } }
                            }
                        }
                    }
                    // The sheen sits over the keys and takes no input, so it
                    // cannot get in the way of a drop.
                    Glass { round: 8; z: 3 }
                }

                // right side strip
                ColumnLayout {
                    spacing: dv.gap
                    visible: backend.sideCellsRight.length > 0
                    Repeater {
                        model: backend.sideLayout["R"] === "single"
                               ? backend.sideCellsRight.slice(0, 1)
                               : backend.sideCellsRight
                        SideCell {
                            ctlKey: modelData
                            tall: backend.sideLayout["R"] === "single"
                        }
                    }
                }

                ColumnLayout {
                    spacing: 20
                    visible: backend.encodersRight.length > 0
                    Repeater {
                        model: backend.encodersRight
                        Encoder { ctlKey: modelData; active: dv.encBound(modelData) }
                    }
                }
            }

            // ---- workspace round buttons (labelled 1..8 like the hardware) ----
            RowLayout {
                id: wsRow
                Layout.alignment: Qt.AlignHCenter
                spacing: 16
                // The first key is the firmware 'circle'; only the label is
                // shifted so the UI reads 1..n like the physical device. A Live
                // S has four of these, a CT and Live eight.
                Repeater {
                    model: backend.workspaceButtons
                    RoundBtn {
                        label: (index + 1).toString()
                        activeColor: theme.ok
                        ctlKey: modelData
                        ledColor: dv.led(modelData)
                        active: backend.selectedWs === modelData
                        switchesWorkspace: true
                        strongActive: true
                    }
                }
            }

            // ---- CT function buttons + big wheel ----
            RowLayout {
                id: wheelZone
                Layout.alignment: Qt.AlignHCenter
                visible: backend.hasWheel   // CT-only: function buttons + wheel
                spacing: 28

                GridLayout {
                    columns: 2; rowSpacing: 14; columnSpacing: 14
                    Layout.alignment: Qt.AlignVCenter
                    Repeater {
                        model: [
                            {l: "⌂", k: "home"}, {l: "↺", k: "undo"},
                            // save sits in the middle row, keyboard below it;
                            // and fn is the *second* column on this cluster.
                            {l: "save", k: "save"}, {l: "↵", k: "enter"},
                            // "⌨" (U+2328) has no glyph in the UI font and
                            // renders as a box, so this one is spelled out.
                            {l: "kbd", k: "keyboard"}, {l: "fn", k: "fnL"}
                        ]
                        RoundBtn { label: modelData.l; ctlKey: modelData.k
                            active: dv.bound(modelData.k); ledColor: dv.led(modelData.k) }
                    }
                }

                // the big round wheel + dial screen (outer ring = dial, inner = wheel).
                // one drop target spans the whole knob; the band under the cursor
                // picks the slot (Touch → wheel, Press/Rotate → dial).
                Rectangle {
                    id: wheelRing
                    width: 180; height: 180; radius: 90
                    // The dial: a machined ring around the screen, which is the
                    // one part of this device everyone recognises.
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: "#43434f" }
                        GradientStop { position: 0.5; color: "#22222a" }
                        GradientStop { position: 1.0; color: "#101015" }
                    }
                    border.color: "#000000"
                    border.width: 1
                    scale: wheelDrop.containsDrag ? 1.03 : 1.0
                    Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
                    TapHandler { onTapped: backend.selectControl("dial") }   // ring selects the dial

                    Knurl { teeth: 120; inset: 2; len: 13; visible: !wheelDrop.containsDrag }

                    // State on the dial is a ring rather than a fill, so the
                    // metal stays metal while it is selected or bound.
                    Rectangle {
                        anchors.centerIn: parent
                        width: parent.width - 4; height: width; radius: width / 2
                        color: "transparent"
                        border.width: dv.isSel("dial") ? 2 : 1
                        border.color: wheelDrop.containsDrag ? theme.accent
                                    : (dv.isSel("dial") ? theme.ok : theme.accent)
                        opacity: (wheelDrop.containsDrag || dv.isSel("dial"))
                                 ? dv.selectedGlow : dv.boundGlow
                        visible: wheelDrop.containsDrag || dv.isSel("dial")
                                 || dv.bound("dial") || dv.bound("dial-l") || dv.bound("dial-r")
                        Behavior on border.color { ColorAnimation { duration: 130 } }
                    }

                    // The bezel the screen sits in, so the glass reads as sunk
                    // into the metal rather than painted on it.
                    Rectangle {
                        anchors.centerIn: parent
                        width: 146; height: 146; radius: 73
                        gradient: Gradient {
                            GradientStop { position: 0.0; color: "#0a0a0e" }
                            GradientStop { position: 1.0; color: "#1c1c24" }
                        }
                    }

                    Rectangle {  // round screen (wheel)
                        anchors.centerIn: parent; width: 142; height: 142; radius: 71
                        color: dv.bg("wheel") !== "" ? dv.bg("wheel") : "#07070a"
                        border.color: dv.isSel("wheel") ? theme.ok
                                    : (dv.bound("wheel") ? theme.accent : "#000000")
                        border.width: dv.isSel("wheel") ? 2 : 1
                        clip: true
                        Behavior on border.color { ColorAnimation { duration: 130 } }
                        TapHandler { onTapped: backend.selectControl("wheel") }
                        // The wheel screen is physically round, so the preview
                        // masks to a circle and fills it. Rectangle.clip only
                        // clips to the bounding box, not the radius, so a plain
                        // clip would still show square corners; and the image
                        // used to be inset to 106px, which drew a small square
                        // floating in a black circle.
                        Item {
                            id: wheelImageArea
                            anchors.fill: parent
                            anchors.margins: 3       // sit inside the bezel
                            visible: dv.img("wheel") != ""
                            layer.enabled: true
                            // Multisampling matters here: without it the mask is
                            // a hard cutout and the circle comes out visibly
                            // stair-stepped.
                            layer.smooth: true
                            layer.samples: 8
                            layer.effect: MultiEffect {
                                maskEnabled: true
                                maskSource: wheelMask
                                // Soften the last fraction of the mask edge so
                                // the rim is not a single hard pixel step.
                                maskThresholdMin: 0.45
                                maskSpreadAtMin: 0.9
                            }
                            Image {
                                anchors.fill: parent
                                source: dv.img("wheel")
                                fillMode: Image.PreserveAspectCrop
                                asynchronous: true
                                smooth: true; mipmap: true
                            }
                        }
                        Item {
                            id: wheelMask
                            anchors.fill: wheelImageArea
                            layer.enabled: true
                            layer.smooth: true
                            layer.samples: 8
                            visible: false
                            Rectangle {
                                anchors.fill: parent
                                radius: width / 2
                                color: "black"
                                antialiasing: true
                            }
                        }
                        Text {
                            anchors.centerIn: parent; text: "WHEEL"
                            visible: dv.img("wheel") == "" && dv.label("wheel") === undefined && dv.bg("wheel") === ""
                            color: theme.muted; font.pixelSize: 12; font.letterSpacing: 2
                        }
                        CtrlLabel { lbl: dv.label("wheel") }
                        Glass { round: 71; z: 4 }
                    }
                    DropArea {
                        id: wheelDrop; anchors.fill: parent
                        property int zone: 0   // 0=touch 1=press 2=rotate◀ 3=rotate▶
                        onPositionChanged: (drag) => {
                            zone = Math.max(0, Math.min(3, Math.floor(drag.y / (height / 4)))) }
                        onDropped: (drop) => {
                            if (!drop.source) return
                            var z = Math.max(0, Math.min(3, Math.floor(drop.y / (height / 4))))
                            var slot = z === 0 ? "wheel" : z === 1 ? "dial" : z === 2 ? "dial-l" : "dial-r"
                            backend.applyLibraryAction(slot, drop.source.aType, drop.source.aValue, drop.source.aLabel)
                        }
                    }
                    Column {   // drop-slot guide
                        anchors.centerIn: parent; visible: wheelDrop.containsDrag; z: 10; spacing: 4
                        Repeater {
                            model: [{t: "Touch", z: 0}, {t: "Press", z: 1},
                                    {t: "Rotate ◀", z: 2}, {t: "Rotate ▶", z: 3}]
                            Rectangle {
                                width: 108; height: 30; radius: 15
                                color: wheelDrop.zone === modelData.z ? theme.accent : Qt.rgba(0, 0, 0, 0.72)
                                border.color: theme.accent
                                border.width: wheelDrop.zone === modelData.z ? 0 : 1
                                Text { anchors.centerIn: parent; text: modelData.t
                                    color: "white"; font.pixelSize: 12; font.bold: true }
                            }
                        }
                    }
                }

                GridLayout {
                    columns: 2; rowSpacing: 14; columnSpacing: 14
                    Layout.alignment: Qt.AlignVCenter
                    Repeater {
                        model: [
                            {l: "A", k: "a"}, {l: "B", k: "b"}, {l: "C", k: "c"},
                            {l: "D", k: "d"},
                            // and the *first* column on the right cluster
                            {l: "fn", k: "fnR"}, {l: "E", k: "e"}
                        ]
                        RoundBtn { label: modelData.l; ctlKey: modelData.k
                            active: dv.bound(modelData.k); ledColor: dv.led(modelData.k) }
                    }
                }
            }
        }
    }
}
