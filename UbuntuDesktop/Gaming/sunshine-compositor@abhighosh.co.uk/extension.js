import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

export default class StreamingCompositorGuard extends Extension {
    enable() {
        global.compositor.disable_unredirect();
    }

    disable() {
        global.compositor.enable_unredirect();
    }
}
