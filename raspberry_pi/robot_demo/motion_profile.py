"""Validated six-axis configuration; unknown angles never become defaults."""

import json
from pathlib import Path

DEFAULT_PROFILE = Path(__file__).with_name("robot_motion_profile.json")
CHANNELS = {"head": 0, "right_shoulder_x": 1, "crown": 2,
            "right_shoulder_y": 3, "left_shoulder_x": 4, "left_shoulder_y": 5}
POSE_AXES = {"greeting": {"head", "right_shoulder_x", "right_shoulder_y"},
             "invitation": {"left_shoulder_x", "left_shoulder_y"}}


class ProfileError(ValueError):
    pass


def _angle(value):
    return type(value) is int and 0 <= value <= 180


class MotionProfile:
    def __init__(self, data):
        self.data = data
        if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
            raise ProfileError("Unsupported motion profile schema")
        if type(data.get("power_verified")) is not bool:
            raise ProfileError("power_verified must be a boolean")
        axes, poses = data.get("axes"), data.get("poses")
        if not isinstance(axes, dict) or set(axes) != set(CHANNELS):
            raise ProfileError("Exactly six named axes are required")
        if not isinstance(poses, dict) or set(poses) != set(POSE_AXES):
            raise ProfileError("Greeting and invitation poses are required")
        for name, channel in CHANNELS.items():
            axis = axes[name]
            if not isinstance(axis, dict) or type(axis.get("channel")) is not int or axis["channel"] != channel:
                raise ProfileError(f"Incorrect channel for {name}")
            if type(axis.get("verified")) is not bool:
                raise ProfileError(f"Missing verification for {name}")
            for key in ("minimum", "maximum", "neutral"):
                if key not in axis or axis[key] is not None and not _angle(axis[key]):
                    raise ProfileError(f"Invalid {name}.{key}")
            low, high = axis["minimum"], axis["maximum"]
            if low is not None and high is not None and low > high:
                raise ProfileError(f"Reversed limits for {name}")
            self.check_angle(name, axis["neutral"])
            self._validate_joint(name)
        for pose, names in POSE_AXES.items():
            if not isinstance(poses[pose], dict) or set(poses[pose]) != names:
                raise ProfileError(f"Incorrect axes for {pose}")
            for name, value in poses[pose].items():
                self.check_angle(name, value)

    def check_angle(self, name, value):
        if value is None:
            return
        if not _angle(value):
            raise ProfileError(f"Invalid target for {name}")
        axis = self.data["axes"][name]
        if axis["minimum"] is not None and value < axis["minimum"]:
            raise ProfileError(f"Target below safe range for {name}")
        if axis["maximum"] is not None and value > axis["maximum"]:
            raise ProfileError(f"Target above safe range for {name}")

    def _validate_joint(self, name):
        axis = self.data["axes"][name]
        if "joint" not in axis:
            return
        joint = axis["joint"]
        keys = {"minimum", "maximum", "neutral", "servo_zero", "direction"}
        if not isinstance(joint, dict) or set(joint) != keys:
            raise ProfileError(f"Invalid joint calibration for {name}")
        for key in ("minimum", "maximum", "neutral"):
            if type(joint[key]) is not int or not -180 <= joint[key] <= 180:
                raise ProfileError(f"Invalid {name}.joint.{key}")
        if not joint["minimum"] <= joint["neutral"] <= joint["maximum"]:
            raise ProfileError(f"Invalid joint limits/neutral for {name}")
        if joint["servo_zero"] is not None and not _angle(joint["servo_zero"]):
            raise ProfileError(f"Invalid servo zero for {name}")
        if joint["direction"] is not None and (type(joint["direction"]) is not int
                                               or joint["direction"] not in (-1, 1)):
            raise ProfileError(f"Invalid servo direction for {name}")
        if joint["servo_zero"] is None or joint["direction"] is None:
            return
        # Relative joint angles never go directly to the Arduino protocol.
        endpoints = [self.servo_angle(name, joint[key]) for key in ("minimum", "maximum")]
        expected = {"minimum": min(endpoints), "maximum": max(endpoints),
                    "neutral": self.servo_angle(name, joint["neutral"])}
        for key, value in expected.items():
            if axis[key] is not None and axis[key] != value:
                raise ProfileError(f"Joint calibration disagrees with {name}.{key}")

    def servo_angle(self, name, joint_angle):
        """Convert a measured relative angle; refuse unknown offsets and directions."""
        joint = self.data["axes"][name].get("joint")
        if not joint or joint["servo_zero"] is None or joint["direction"] is None:
            raise ProfileError(f"Joint calibration required for {name}")
        if type(joint_angle) is not int or not joint["minimum"] <= joint_angle <= joint["maximum"]:
            raise ProfileError(f"Joint target outside safe range for {name}")
        value = joint["servo_zero"] + joint["direction"] * joint_angle
        self.check_angle(name, value)
        return value

    def joint_targets(self, targets):
        """Convert each joint independently; mirrored arms need opposite PWM angles."""
        if not isinstance(targets, dict) or not targets or set(targets) - set(CHANNELS):
            raise ProfileError("Joint targets must name known axes")
        return {CHANNELS[name]: self.servo_angle(name, angle) for name, angle in targets.items()}

    def missing(self, include_poses=True):
        missing = [] if self.data["power_verified"] else ["power_verified"]
        for name, axis in self.data["axes"].items():
            for key in ("minimum", "maximum", "neutral"):
                if axis[key] is None:
                    missing.append(f"{name}.{key}")
            if not axis["verified"]:
                missing.append(f"{name}.verified")
            if "joint" in axis:
                for key in ("servo_zero", "direction"):
                    if axis["joint"][key] is None:
                        missing.append(f"{name}.joint.{key}")
        if include_poses:
            for pose, targets in self.data["poses"].items():
                missing.extend(f"{pose}.{name}" for name, angle in targets.items() if angle is None)
        return missing

    def require_ready(self, include_poses=True):
        missing = self.missing(include_poses)
        if missing:
            raise ProfileError("Hardware execution refused; confirm: " + ", ".join(missing))

    def targets(self, pose):
        if pose == "startup":
            names = set(CHANNELS)
        elif pose == "home":
            names = set(CHANNELS) - {"crown"}
        else:
            return {CHANNELS[name]: angle for name, angle in self.data["poses"][pose].items()}
        return {CHANNELS[name]: self.data["axes"][name]["neutral"] for name in sorted(names)}

    def limits(self):
        return {axis["channel"]: (axis["minimum"], axis["maximum"])
                for axis in self.data["axes"].values()}


def load_profile(path=DEFAULT_PROFILE):
    with Path(path).open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ProfileError("Motion profile must be an object")
    return MotionProfile(data)
