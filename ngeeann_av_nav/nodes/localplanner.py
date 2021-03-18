#!/usr/bin/env python3

import rclpy
import numpy as np

from rclpy.node import Node
from geometry_msgs.msg import PoseStamped, Quaternion, Pose2D
from ngeeann_av_msgs.msg import Path2D, State2D
from nav_msgs.msg import Path, OccupancyGrid, MapMetaData
from std_msgs.msg import Float32
from heading2quaternion import heading_to_quaternion
from cubic_spline_planner import *

class LocalPathPlanner(Node):

    def __init__(self):
        ''' 
        Class constructor to initialise the class 
        '''

        super().__init__('local_planner')

        # Initialise publishers
        self.local_planner_pub = self.create_publisher(Path2D, '/ngeeann_av/path', 10)
        self.path_viz_pub = self.create_publisher(Path, '/ngeeann_av/viz_path', 10)
        self.target_vel_pub = self.create_publisher(Float32, '/ngeeann_av/target_velocity', 10)

        # Initialise subscribers
        # self.goals_sub = self.create_subscription(Path2D, '/ngeeann_av/goals', self.goals_cb, 10)
        self.localisation_sub = self.create_subscription(State2D, '/ngeeann_av/state2D', self.vehicle_state_cb, 10)
        self.gridmap_sub = self.create_subscription(OccupancyGrid, '/map', self.gridmap_cb, 10)

        # Load parameters
        try:
            self.declare_parameters(
                namespace='',
                parameters=[
                    ('update_frequency', None),
                    ('frame_id', None),
                    ('car_width', None),
                    ('centreofgravity_to_frontaxle', None)
                ]
            )

            self.frequency = float(self.get_parameter("update_frequency").value)
            self.frame_id = str(self.get_parameter("frame_id").value)
            self.car_width = float(self.get_parameter("car_width").value)
            self.cg2frontaxle = float(self.get_parameter("centreofgravity_to_frontaxle").value)

        except:
            raise Exception("Missing ROS parameters. Check the configuration file.")

        # Class constants
        self.ds = 1 / self.frequency
        self.origin_x = 0
        self.origin_y = 0

        # Class variables to use whenever within the class when necessary
        self.target_vel = 3.0
        # self.ax = []
        # self.ay = []
        self.ax = [103.67, 102.6610906864386, 99.65400001792553, 94.70725759380844, 87.91714612853669]
        self.ay = [0, 14.428075376529984, 28.575324677548302, 42.16638778766821, 54.93673012305635]
        self.gmap = OccupancyGrid()

    def goals_cb(self, msg):
        '''
        Callback function to recieve immediate goals from global planner in global frame
        '''
        self.ax = []
        self.ay = []
        
        for i in range(0, len(msg.poses)):
            px = msg.poses[i].x
            py = msg.poses[i].y
            self.ax.append(px)
            self.ay.append(py)

        print("\nGoals received: {}".format(len(msg.poses)))

    def vehicle_state_cb(self, msg):
        ''' 
        Callback function to recieve vehicle state information from localization in global frame
        '''
        self.x = msg.pose.x
        self.y = msg.pose.y
        self.yaw = msg.pose.theta

    def gridmap_cb(self, msg):
        ''' 
        Callback function to recieve map data
        '''
        self.gmap = msg

    def target_index_calculator(self, cx, cy):  
        ''' 
        Calculates closest point along the path to vehicle front axle
        '''
        # Calculate position of the front axle
        fx = self.x + self.cg2frontaxle * -np.sin(self.yaw)
        fy = self.y + self.cg2frontaxle * np.cos(self.yaw)

        dx = [fx - icx for icx in cx] # Find the x-axis of the front axle relative to the path
        dy = [fy - icy for icy in cy] # Find the y-axis of the front axle relative to the path

        d = np.hypot(dx, dy) # Find the distance from the front axle to the path
        reference_idx = np.argmin(d) # Find the shortest distance in the array
        return reference_idx

    def determine_path(self, cx, cy, cyaw):
        ''' 
        Map function to validate and determine a path by the following steps:

        1: Identify vehicle's progress along path, search all points ahead for potential collisions
        2: Draft a collision avoidance strategy
        '''
        # Initializing map information
        width = self.gmap.info.width
        height = self.gmap.info.height
        resolution = self.gmap.info.resolution
        origin_x = self.origin_x
        origin_y = self.origin_y
        collisions = []
        collide_id = None

        # Current vehicle progress along path
        lateral_ref_id = self.target_index_calculator(cx, cy)

        #  Validates path of collisions
        for n in range(self.react_dist, len(cyaw) - self.react_dist - 1):

            # Draws side profile of the vehicle along the path ahead
            for i in np.arange(-0.5 * self.car_width, 0.5 * self.car_width, resolution):
                ix = int((cx[n] + i*np.cos(cyaw[n] - 0.5 * np.pi) - origin_x) / resolution)
                iy = int((cy[n] + i*np.sin(cyaw[n] - 0.5 * np.pi) - origin_y) / resolution)
                p = iy * width + ix
                if (self.gmap.data[p] != 0):
                    collisions.append(n)
        
        if len(collisions) != 0:
            
            cx, cy, cyaw = self.collision_avoidance(collisions, cx, cy, cyaw)

        return cx, cy, cyaw, collisions

    def create_viz_path(self):
        ''' 
        Publish paths to RViz
        '''
        # Validated path returned
        cx, cy, cyaw, collisions = self.determine_path(ocx, ocy, ocyaw)

        cells = min(len(cx), len(cy), len(cyaw))
        target_path = Path2D()
        
        viz_path = Path()
        viz_path.header.frame_id = "map"
        viz_path.header.stamp = self.get_clock().now().to_msg()

        for n in range(0, cells):
            # Appending to Target Path
            npose = Pose2D()
            npose.x = cx[n]
            npose.y = cy[n]
            npose.theta = cyaw[n]
            target_path.poses.append(npose)

            # Appending to Visualization Path
            vpose = PoseStamped()
            vpose.header.frame_id = self.frame_id
            vpose.header.seq = n
            vpose.header.stamp = self.get_clock().now().to_msg()
            vpose.pose.position.x = cx[n]
            vpose.pose.position.y = cy[n]
            vpose.pose.position.z = 0.0
            vpose.pose.orientation = heading_to_quaternion(np.pi * 0.5 - cyaw[n])
            viz_path.poses.append(vpose)

        self.path_viz_pub.publish(viz_path)

    def create_target_path(self):
        '''
        Default path draw across waypoints
        '''
        ocx, ocy, ocyaw = calc_spline_course(self.ax, self.ay, self.ds)

def main(args=None):
    ''' 
    Main function to initialise the class and node. 
    '''

    # Initialise the node
    rclpy.init(args=args)

    # Initialise the class
    local_planner = LocalPathPlanner()

    while rclpy.ok():
        try:
            target_path = local_planner.create_target_path()
            local_planner.target_vel_pub.publish(local_planner.target_vel)

            rclpy.spin(local_planner)

        except KeyboardInterrupt:
            print("\n")
            print("Shutting down ROS node...")

if __name__=="__main__":
    main()