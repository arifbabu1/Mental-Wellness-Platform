/*
 * Compatibility shim.
 *
 * The consultation room now uses the Jitsi Meet IFrame API from
 * home/templates/consultation/room.html. This file intentionally avoids any
 * the old peer-to-peer call engine.
 */
class WebRTCConsultation {
    constructor() {
        this.isDisabled = true;
    }

    initialize() {
        console.info('Custom WebRTC is disabled. Jitsi Meet handles video consultations.');
    }

    cleanup() {}
}

window.WebRTCConsultation = WebRTCConsultation;
