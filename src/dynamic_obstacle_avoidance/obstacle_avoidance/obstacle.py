#!/USSR/bin/python3

'''
@date 2019-10-15
@author Lukas Huber 
@email lukas.huber@epfl.ch
'''

import time
import numpy as np
from math import sin, cos, pi, ceil
import warnings, sys

import numpy.linalg as LA

# import quaternion # numpy-quaternion 
# import dynamic_obstacle_avoidance

from dynamic_obstacle_avoidance.obstacle_avoidance.angle_math import *

from dynamic_obstacle_avoidance.obstacle_avoidance.state import State

from dynamic_obstacle_avoidance.obstacle_avoidance.modulation import *

# TODO: remove following two? For Compability
# from dynamic_obstacle_avoidance.obstacle_avoidance.obs_common_section import *
# from dynamic_obstacle_avoidance.obstacle_avoidance.obs_dynamic_center_3d import *

# TODO: remove after debugging/developping
import matplotlib.pyplot as plt

# import quaternion 

visualize_debug = False


class Obstacle(State):
    """ 
    (Virtual) base class of obstacles 
    """
    # TODO -- enforce certain functions
    id_counter = 0
    active_counter = 0
    
    def __repr__(self):
        return "Obstacle <<{}>> is of Type: {}".format(self.name, type(self))

    def __init__(self, orientation=0, sigma=1,  center_position=[0,0],
                 tail_effect=True, sf=1,
                 name=None,
                 # margin_absolut=0, 
                 x0=None, th_r=None, dimension=None,
                 linear_velocity=None, angular_velocity=None, xd=None, w=None,
                 func_w=None, func_xd=None,  x_start=0, x_end=0, timeVariant=False,
                 Gamma_ref=0, is_boundary=False, hirarchy=0, ind_parent=-1):
                 # *args, **kwargs): # maybe random arguments
        # This class defines obstacles to modulate the DS around it
        # At current stage the function focuses on Ellipsoids, but can be extended to more general obstacles
        if name is None:
            self.name = "obstacle{}".format(Obstacle.id_counter)
        else:
            self.name = name
            
        self.sf = sf # TODO - rename
        # self.delta_margin = delta_margin
        
        self.sigma = sigma
        self.tail_effect = tail_effect # Modulation if moving away behind obstacle

        # Obstacle attitude
        if type(x0) != type(None):
            center_position = x0 # TODO remove and rename
        self.position = center_position
        self.center_position = self.position
        
        self.x0 = center_position
        
        self.dim = len(self.center_position) # Dimension of space
        self.d = len(self.center_position) # Dimension of space # TODO remove
        
        if type(th_r)!= type(None):
            orientation = th_r
        self.orientation = orientation

        self.rotMatrix = []
        self.compute_R() # Compute Rotation Matrix

        self.resolution = 0 #Resolution of drawing

        self._boundary_points = None # Numerical drawing of obstacle boundarywq
        self._boundary_points_margin = None # Obstacle boundary plus margin!

        self.timeVariant = timeVariant
        if self.timeVariant:
            self.func_xd = 0
            self.func_w = 0
        # else:
            # self.always_moving = always_moving
        
        if angular_velocity is None:
            if w is None:
                if self.dim==2:
                    angular_velocity = 0
                elif self.dim==3:
                    angular_velocity = np.zeros(self.dim)
                else:
                    import pdb; pdb.set_trace();
                    raise ValueError("Define angular velocity for higher dimensions.")
            else:
                angular_velocity = w
        self.angular_velocity = angular_velocity
        self.w = self.angular_velocity # TOOD - remove

        if linear_velocity is None:
            if xd is None:
                linear_velocity=np.zeros(self.dim)
            else:
                linear_velocity = xd
        self.linear_velocity = linear_velocity
        self.xd = self.linear_velocity
        
        # Special case of moving obstacle (Create subclass)
        if sum(np.abs(self.linear_velocity)) or np.sum(self.angular_velocity) \
           or self.timeVariant:
            # Dynamic simulation - assign varibales:
            self.x_start = x_start
            self.x_end = x_end
            self.always_moving = False
        else:
            self.x_start = 0
            self.x_end = 0

        self.update_timestamp()

        # Trees of stars // move to 'properties'
        self.hirarchy = hirarchy
        self.ind_parent = ind_parent
        self.ind_children = []

        # Relative Reference point // Dyanmic center
        self.reference_point = np.zeros(self.dim) # TODO remove and rename
        self.reference_point_is_inside = True

        self.Gamma_ref = Gamma_ref
        self.is_boundary = is_boundary

        self.is_convex = False # Needed?
        # If
        # self.properties = {} # TODO: use kwargs

        Obstacle.id_counter += 1 # New obstacle created
        Obstacle.active_counter += 1
        self._center_dyn  = []

    def __del__(self):
        Obstacle.active_counter -= 1

    @property
    def dimension(self):
        return self.dim
    @property
    def center_dyn(self):# TODO: depreciated -- delete
        return self.reference_point
    @center_dyn.setter
    def center_dyn(self, value):
        # Rename kernel-point?
        self._center_dyn = value
        self.reference_point = self._center_dyn      
    
    @property
    def global_reference_point(self):
        # Rename kernel-point?
        return self.transform_relative2global(self._reference_point)
    
    @property
    def local_reference_point(self):
        # Rename kernel-point?
        return self._reference_point

    @local_reference_point.setter
    def local_reference_point(self, value):
        # Rename kernel-point?
        self._reference_point = value
        
    @property
    def reference_point(self):
        # Rename kernel-point?
        return self._reference_point

    @reference_point.setter
    def reference_point(self, value):
        self._reference_point = value

    @property
    def orientation(self):
        return self._orientation
    
    @orientation.setter
    def orientation(self, value):
        if isinstance(value, list) and self.dim==3:
            self._orientation = np.array(value) # TODO: change to quaternion
        else:
            self._orientation = value
        self.compute_R()

    @property
    def position(self):
        return self.center_position

    @position.setter
    def position(self, value):
        self.center_position = value
    
    @property
    def center_position(self):
        return self._center_position
    
    @center_position.setter
    def center_position(self, value):
        if isinstance(value, list):
            self._center_position = np.array(value) 
        else:
            self._center_position = value

    @property
    def th_r(self): # TODO: will be removed since outdated
        return self.orientation # getter

    @th_r.setter
    def th_r(self, value): # TODO: will be removed since outdated
        self.orientation = value # setter

    @property
    def timestamp(self):
        return self._timestamp

    @timestamp.setter
    def timestamp(self, value):
        # if timestamp is None:
        self._timestamp = value

    def update_timestamp(self):
        self._timestamp = time.time()

    @property
    def linear_velocity(self):
        return self._linear_velocity

    @linear_velocity.setter
    def linear_velocity(self, value):
        if len(value)>2:
            import pdb; pdb.set_trace()
        self._linear_velocity = value

    @property
    def boundary_points(self):
        return self._boundary_points

    @boundary_points.setter
    def boundary_points(self, value):
        self._boundary_points = value
        
    @property
    def boundary_points_local(self):
        return self._boundary_points

    @boundary_points_local.setter
    def boundary_points_local(self, value):
        self._boundary_points = value

    @property
    def x_obs(self):
        return self.boundary_points_global_closed

    @property
    def boundary_points_global_closed(self):
        boundary = self.boundary_points_global
        return np.hstack((boundary, boundary[:, 0:1]))

    @property
    def boundary_points_global(self):
        return self.transform_relative2global(self._boundary_points)

    # @property
    # def boundary_points_margin(self):
        # return self._boundary_points_margin
    
    # @boundary_points_margin.setter
    # def boundary_points_margin(self, value):
        # self._boundary_points_margin = value

    @property
    def boundary_points_margin_local(self):
        return self._boundary_points_margin
    
    @boundary_points_margin_local.setter
    def boundary_points_margin_local(self, value):
        self._boundary_points_margin = value

    @property
    def x_obs_sf(self):
        return self.boundary_points_margin_global_closed
    
    @property
    def boundary_points_margin_global(self):
        # import pdb; pdb.set_trace() ## DEBUG ##
        return self.transform_relative2global(self._boundary_points_margin)

    @property
    def boundary_points_margin_global_closed(self):
        boundary = self.boundary_points_margin_global
        return np.hstack((boundary, boundary[:, 0:1]))

    # @boundary_points.setter
    # def boundary_points
    
    # def position_array_wrapper(self, func, position, *args, **kwargs):
    def get_gamma(self, position_, *args, **kwargs):
        ''' Get gamma value of obstacle '''
        position = np.array(position_)
        if len(position.shape)==1:
            position = np.reshape(position, (self.dim, 1))
            # import pdb; pdb.set_trace() ## DEBUG ##
            
            return np.reshape(self._get_gamma(position, *args, **kwargs), (-1))
            
        elif len(position.shape)==2:
            return self._get_gamma(position, *args, **kwargs)
                              
        else:
            ValueError("Triple dimensional position are unexpected")

    # def __del__(self):
        # ''' Destructor '''
        # Obstacle.active_counter -= 1
    
    def _get_gamma(self, position, reference_point=None, in_global_frame=False, gamma_type='proportional'):
        '''
        Calculates the norm of the function.

        Position input has to be 2-dimensional array
        '''
        if in_global_frame:
            position = self.transform_global2relative(position)
            if not reference_point is None:
                reference_point = self.transform_global2relative(reference_point)

        if reference_point is None:
            reference_point = self.local_reference_point
        else:
            if self.get_gamma(reference_point) > 0:
                raise ValueError("Reference point is outside hull")

        dist_position = np.linalg.norm(position, axis=0)
        ind_nonzero = dist_position>0

        if not np.sum(ind_nonzero): # only zero values
            if self.is_boundary:
                return np.ones(dist_position.shape)*sys.float_info.max
            else:
                return np.zeros(dist_position.shape)
        
        gamma = np.zeros(dist_position.shape)
        
        radius = self._get_local_radius(position[:, ind_nonzero], reference_point)
        
        if gamma_type=='proportional':
            gamma[ind_nonzero] = dist_position[ind_nonzero]/radius[ind_nonzero]

        elif gamma_type=='linear':
            gamma[ind_nonzero] = 1 + (dist_position[ind_nonzero]-radius[ind_nonzero])/self.get_reference_length()
            
        else:
            raise NotImplementedError("Not implemented for other gamma types.")

        if self.is_boundary:
            if gamma_type=='proportional':
                gamma[ind_nonzero] = 1/gamma[ind_nonzero]
                gamma[~ind_nonzero] = sys.float_info.max
                
            else:
                raise NotImplementedError("Not implemented for other gamma types.")

        return gamma
        
    # def get_gamma(self, *args, **kwargs):
                
        # raise NotImplementedError("Child of type {} needs an Implemenation of virtual class.".format(type(self)))

    def draw_obstacle(self, *args, **kwargs):
        raise NotImplementedError("Child of type {} needs an Implemenation of virtual class.".format(type(self)))

    
    def transform_global2relative(self, position):
        if isinstance(position, (list)):
            position = np.array(position)
        elif not isinstance(position, (list, np.ndarray)):
            raise TypeError('Position={} is of type {}'.format(position, type(position)))
            
        if not position.shape[0]==self.dim:
            raise ValueError("Wrong position dimensions")
            
        if len(position.shape)==1:
            return self.rotMatrix.T.dot(position - np.array(self.center_position))
        elif len(position.shape)==2:
            n_points = position.shape[1]
            return self.rotMatrix.T.dot(position - np.tile(self.center_position, (n_points,1)).T)
        else:
            raise ValueError("Unexpected position-shape")


    def transform_relative2global(self, position):
        if isinstance(position, (list)):
            position = np.array(position)
        elif not isinstance(position, (list, np.ndarray)):
            raise TypeError('Position={} is of type {}'.format(position, type(position)))
            
        if not position.shape[0]==self.dim:
            raise TypeError('Position is of dimension {}, instead of {}'.format(position.shape[0], self.dim))

        if len(position.shape)==1:
            return self.rotMatrix.dot(position) + self.center_position
        elif len(position.shape)==2:
            # TODO - make it a oneliner without for loop to speed up
            # for ii in range(position.shape[1]):
                # position[:, ii] = self.rotMatrix.dot(position[:, ii]) + self.center_position
            # return position
            n_points = position.shape[1]
            return self.rotMatrix.dot(position) + np.tile(self.center_position, (n_points,1)).T
        # return (self.rotMatrix.dot(position))  + np.array(self.center_position)
        else:
            raise ValueError("Unexpected position-shape")
        
    def transform_relative2global_dir(self, direction):
        if isinstance(direction, (list)):
            direction = np.array(direction)
        elif not isinstance(direction, (list, np.ndarray)):
            raise TypeError('Direction={} is of type {}'.format(direction, type(direction)))
        
        if self.dim > 3:
            warnings.warn("Not implemented for higer dimensions")
            return direction
        return self.rotMatrix.dot(direction)

    def transform_global2relative_dir(self, direction):
        if isinstance(direction, (list)):
            direction = np.array(direction)
        elif not isinstance(direction, (list, np.ndarray)):
            raise TypeError('Direction={} is of type {}'.format(direction, type(direction)))
        
        if self.dim > 3:
            warnings.warn("Not implemented for higer dimensions")
            return direction
        return self.rotMatrix.T.dot(direction)

    
    def compute_R(self):
        # TODO - replace with quaternions
        # Find solution for higher dimensions
        orientation = self._orientation

        # Compute the rotation matrix in 2D and 3D
        if orientation is None:
            self.rotMatrix = np.eye(self.dim)
            return

        # rotating the query point into the obstacle frame of reference
        if self.dim==2:
            self.rotMatrix = np.array([[cos(orientation), -sin(orientation)], 
                                       [sin(orientation),  cos(orientation)]])
                                       
        elif self.dim==3:
            R_x = np.array([[1, 0, 0,],
                        [0, np.cos(orientation[0]), np.sin(orientation[0])],
                        [0, -np.sin(orientation[0]), np.cos(orientation[0])] ])

            R_y = np.array([[np.cos(orientation[1]), 0, -np.sin(orientation[1])],
                        [0, 1, 0],
                        [np.sin(orientation[1]), 0, np.cos(orientation[1])] ])

            R_z = np.array([[np.cos(orientation[2]), np.sin(orientation[2]), 0],
                        [-np.sin(orientation[2]), np.cos(orientation[2]), 0],
                        [ 0, 0, 1] ])

            self.rotMatrix= R_x.dot(R_y).dot(R_z)
        else:
            warnings.warn('rotation not yet defined in dimensions d > 3 !')
            self.rotMatrix = np.eye(self.dim)

    def set_reference_point(self, position, in_global_frame=False): # Inherit
        """Defines reference point. 
        It is used to create reference direction for the modulation of the system."""
        
        if in_global_frame:
            position = self.transform_global2relative(position)
            
        # self.reference_point = position
        self.reference_point = np.array(position)
        self.extend_hull_around_reference()
        
    def move_obstacle_to_referencePoint(self, position, in_global_frame=True):
        if not in_global_frame:
            position = self.transform_relative2global(position)

        self.center_position = position
        
        # self.reference_point = position
        # self.center_dyn = self.reference_point
        

    def move_center(self, position, in_global_frame=True):
        ''' Change (center) position of the system. 
        Note that all other variables are relative.'''
        if not in_global_frame:
            position = self.transform_relative2global(position)
        
        self.center_position = position


    def update_position_and_orientation(self, position, orientation, k_position=0.9, k_linear_velocity=0.9, k_orientation=0.9, k_angular_velocity=0.9, time_current=None, reset=False):
        ''' Updates position and orientation. Additionally calculates linear and angular velocity based on the passed timestep. 
        Updated values for pose and twist are filetered.

        Input: 
        - Position (2D) & 
        - Orientation (float)  '''
        
        if self.dim>2:
            raise NotImplementedError("Implement for dimension >2.")

        # TODO implement Kalman filter
        if time_current is None:
            time_current = time.time()
            
        if reset:
            self.center_position = position
            self.orientation = orientation
            self.linear_velocity = np.zeros(self.dim)
            self.angular_velocity = np.zeros(self.dim)
            self.draw_obstacle()
            return 
        
        dt = time_current - self.timestamp
        
        if isinstance(position, list):
            position = np.array(position)

        if self.dim==2:
            # 2D navigation, but 3D sensor input
            new_linear_velocity = (position-self.position)/dt
            
            # Periodicity of oscillation
            delta_orientation = angle_difference_directional(orientation, self.orientation)
            new_angular_velocity = delta_orientation/dt
            # print('new orientation = {} // old orentation = {}'.format(np.round(orientation*180/pi, 2), np.round(self.orientation*180/pi, 2)))
            # print('delta orientation', np.round(delta_orientation*180/pi, 2))

            self.linear_velocity = k_linear_velocity*self.linear_velocity + (1-k_linear_velocity)*new_linear_velocity
            self.center_position = k_position*(self.linear_velocity*dt + self.center_position) + (1-k_position)*(position)

            # Periodic Weighted Average
            # print('angular vel: old={} --- new={}'.format(np.round(self.angular_velocity, 2), np.round(new_angular_velocity, 2)))
            self.angular_velocity = k_angular_velocity*self.angular_velocity + (1-k_angular_velocity)*new_angular_velocity 

            # print('final vel={} // dt={}'.format(self.angular_velocity, dt))
            # print('step', self.angular_velocity*dt)
            # print('orientation', orientation)
            # print('prediced or', self.angular_velocity*dt + self.orientation)
            self.orientation = periodic_weighted_sum(
                angles=[self.angular_velocity*dt+self.orientation, orientation],
                weights=[k_orientation, (1-k_orientation)] )
            
            # self.orientation = (k_orientation*(orientation) + (1-k_orientation)*(self.angular_velocity*dt + self.orientation) ) # TODO: UPDATE ORIENTATION ROTATIONAL
            # self.orientation = angle_modulo(self.orientation)
            #TODO add filter
        self.timestamp = time_current

        self.draw_obstacle()

    def are_lines_intersecting(self, direction_line, passive_line):
        # TODO only return intersection point or None
        # solve equation line1['point_start'] + a*line1['direction'] = line2['point_end'] + b*line2['direction']
        connection_direction = np.array(direction_line['point_end']) - np.array(direction_line['point_start'])
        connection_passive = np.array(passive_line['point_end']) - np.array(passive_line['point_start'])
        connection_matrix = np.vstack((connection_direction, -connection_passive)).T
        
        if LA.det(connection_matrix): # nonzero value
            direction_factors = (LA.inv(connection_matrix).dot(
                                 np.array(passive_line['point_start'])
                                  - np.array(direction_line['point_start']) ))

            # Smooth because it's a tangent
            if direction_factors[0]>=0:
                if direction_factors[1]>=0 and LA.norm(direction_factors[1]*connection_passive) <= LA.norm(connection_passive):

                    return True, LA.norm(direction_factors[0]*connection_direction)
 
        if False: # show plot
            dir_start = self.transform_relative2global(direction_line['point_start'])
            dir_end = self.transform_relative2global(direction_line['point_end'])

            pas_start = self.transform_relative2global(passive_line['point_start'])
            pas_end = self.transform_relative2global(passive_line['point_end'])

            plt.ion()
            plt.plot([dir_start[0], dir_end[0]], [dir_start[1], dir_end[1]], 'g--')
            plt.plot([pas_start[0], pas_end[0]], [pas_start[1], pas_end[1]], 'r--')
            plt.show()
            print('done intersections')

        return False, -1


    def get_obstacle_radius(self, position, in_global_frame=False, Gamma=None): # Inherit
        # TODO: remove since looping...
        if in_global_frame:
            position = self.transform_global2relative(position)

        if not Gamma==None:
            Gamma = self.get_gamma(position)
        dist_to_center = LA.norm(position)

        return dist_to_center/Gamma
    

    def get_reference_point(self, in_global_frame=False): # Inherit
        if in_global_frame:
            return self.transform_relative2global(self.reference_point)
        else:
            return self.reference_point
    

    def get_boundaryGamma(self, Gamma, Gamma_ref=0):
        '''
        Reverse Gamma value such that boundaries can be treated with the same algorithm
        as obstacles

        Basic rule: [1, oo] -> [1, 0] AND [0, 1] -> [oo, 1]
        '''

        if isinstance(Gamma, (float, int)):
            if Gamma <= Gamma_ref:
                return sys.float_info.max
            else:
                return (1-Gamma_ref)/(Gamma-Gamma_ref)
            
        else:
            if isinstance(Gamma, (list)):
                Gamma = np.array(Gamma)
            ind_small_gamma = (Gamma <= Gamma_ref)
            Gamma[ind_small_gamma] = sys.float_info.max
            Gamma[~ind_small_gamma] = (1-Gamma_ref)/(Gamma[~ind_small_gamma]-Gamma_ref)
            return Gamma

        
    def get_angle2dir(self, position_dir, tangent_dir, needs_normalization=True):
        if needs_normalization:
            if len(position_dir.shape) > 1:
                position_dir /= np.tile(LA.norm(position_dir,axis=0), (self.dim, 1))
                tangent_dir /= np.tile(LA.norm(tangent_dir, axis=0), (self.dim, 1))
                angle_arccos = np.sum(position_dir * tangent_dir, axis=0)
            else:
                position_dir /= LA.norm(position_dir)
                tangent_dir /= LA.norm(tangent_dir)
                angle_arccos = np.sum(position_dir * tangent_dir)
        return np.arccos(angle_arccos)


    def get_angle_weight(self, angles, max_angle=pi, min_angle=0, check_range=False, weight_pow=1):
        # n_angless = np.array(angles).shape[0]
        if check_range:
            ind_low = angles <= min_angle
            if np.sum(ind_low):
                return ind_low/np.sum(ind_low)

            angles = np.min(np.vstack((angles, np.ones(n_angles)*max_angle)) )

        zero_ind = angles<=min_angle
        if np.sum(zero_ind):
            return zero_ind/np.sum(zero_ind)

        nonzero_ind = angles<max_angle
        if not np.sum(nonzero_ind):
            warnings.warn("No angle has an influence")
            # print('Angles', angles)
            return np.zeros(angles.shape)
        
        elif np.sum(nonzero_ind)==1:
            return nonzero_ind*1.0
        
        # [min, max] -> [0, 1] weights
        weights = (angles[nonzero_ind]-min_angle)/(max_angle-min_angle)
        
        # [min, max] -> [infty, 1]
        weights = 1/weights

        # [min, max] -> [infty, 0]
        weights = (weights - 1)**weight_pow

        weight_norm = np.sum(weights)
        
        if weight_norm:
            weights =  weights/weight_norm

        weights_all = np.zeros(angles.shape)
        weights_all[nonzero_ind] = weights 
        return weights_all

    
    def get_distance_weight(self, distance, power=1, distance_min=0):
        ind_positiveDistance = (distance>0)

        distance = distance - distance_min
        weights = np.zeros(distance.shape)
        weights[ind_positiveDistance] = (1./distance[ind_positiveDistance])**power
        weights[ind_positiveDistance] /= np.sum(weights[ind_positiveDistance])
        # weights[~ind_positiveDistance] = 0
        return weights

    
    def draw_reference_hull(self, normal_vector, position):
        pos_abs = self.transform_relative2global(position)
        norm_abs = self.transform_relative2global_dir(normal_vector)

        plt.quiver(pos_abs[0], pos_abs[1], norm_abs[0], norm_abs[1], color='k', label="Normal")

        ref_dir = self.transform_relative2global_dir(self.get_reference_direction(position, in_global_frame=False, normalize=True))

        plt.quiver(pos_abs[0], pos_abs[1], ref_dir[0], ref_dir[1], color='g', label="Reference")

        ref_abs = self.transform_relative2global(self.hull_edge)

        for ii in range(2):
            tang_abs = self.transform_relative2global(self.tangent_points[:, ii])
            plt.plot([tang_abs[0], ref_abs[0]], [tang_abs[1], ref_abs[1]], 'k--')
        
    def get_reference_direction(self, position, in_global_frame=False, normalize=True):
        # Inherit
        # if in_global_frame:
            # position = self.transform_global2relative(position)

        if hasattr(self, 'reference_point') or hasattr(self,'center_dyn'):  # automatic adaptation of center
            ref_point = self.global_reference_point if in_global_frame else self.local_reference_point
            if len(position.shape)==1:
                reference_direction = - (position - ref_point)
            else:
                reference_direction = - (position - np.tile(ref_point, (position.shape[1], 1)).T)
        else:
            reference_direction = - position

        if normalize:
            if len(position.shape)==1:
                ref_norm = LA.norm(reference_direction)
                if ref_norm>0:
                    reference_direction = reference_direction/ref_norm 
            else:
                ref_norm = LA.norm(reference_direction, axis=0)
                ind_nonzero = ref_norm>0
                reference_direction[:, ind_nonzero] = reference_direction[:, ind_nonzero]/ref_norm[ind_nonzero]

        # if in_global_frame:
            # reference_direction = self.transform_global2relative_dir(reference_direction)

        return reference_direction

    
    def update_pos(self, t, dt, x_lim=[], y_lim=[]):
        # Inherit
        # TODO - implement function dependend movement (yield), nonlinear integration
        # Euler / Runge-Kutta integration

        if self.always_moving or self.x_end > t :
            if self.always_moving or self.x_start<t:
                # Check if xd and w are functions
                if self.timeVariant:
                    # TODO - implement RK4 for movement

                    self.xd = self.func_xd(t)
                    self.w = self.func_w(t)

                self.center_position = [self.center_position[i] + dt*self.xd[i] for i in range(self.d)] # update position

                if len(x_lim):
                    self.center_position[0] = np.min([np.max([self.center_position[0], x_lim[0]]), x_lim[1]])
                if len(y_lim):
                    self.center_position[1] = np.min([np.max([self.center_position[1], y_lim[0]]), y_lim[1]])

                if self.w: # if new rotation speed

                    if self.d <= 2:
                        self.th_r = self.th_r + dt*self.w  #update orientation/attitude
                    else:
                        self.th_r = [self.th_r[i]+dt*self.w[i] for i in range(self.d)]  #update orientation/attitude
                    self.compute_R() # Update rotation matrix

                self.draw_obstacle()

    def get_scaled_boundary_points(self, scale, safety_margin=True, redraw_obstacle=False):
        # Draws at 1:scale
        if safety_margin:
            scaled_boundary_points = scale*self._boundary_points_margin
        else:
            scaled_boundary_points = scale*self._boundary_points
            
        return self.transform_relative2global(scaled_boundary_points)
        
    def obs_check_collision(self, ):
        print('TODO: check class')
        raise NotImplementedError()

    def get_distance_to_hullEdge(self, position, hull_edge=None):
        raise NotImplementedError()

